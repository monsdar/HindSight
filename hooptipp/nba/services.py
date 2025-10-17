"""NBA-specific services for syncing teams, players, and games."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from balldontlie.exceptions import BallDontLieException
from django.utils import timezone

from hooptipp.predictions.models import Option, OptionCategory

from .client import CachedBallDontLieAPI, build_cached_bdl_client
from .managers import NbaPlayerManager, NbaTeamManager

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Summary of a synchronization run."""

    created: int = 0
    updated: int = 0
    removed: int = 0

    @property
    def changed(self) -> bool:
        """Return True when the sync modified the database."""
        return any((self.created, self.updated, self.removed))


# The BallDontLie free tier allows 5 requests per minute. A throttle of 12.5
# seconds leaves a small safety margin between requests.
PLAYER_SYNC_THROTTLE_SECONDS = 12.5

_BDL_CLIENT_CACHE: dict[str, CachedBallDontLieAPI] = {}
_BDL_CLIENT_LOCK = threading.Lock()


def _get_bdl_api_key() -> str:
    """Return the configured BallDontLie API token formatted for requests."""

    def _candidates():
        yield os.environ.get("BALLDONTLIE_API_TOKEN", "")
        yield os.environ.get("BALLDONTLIE_API_KEY", "")

    for raw_value in _candidates():
        token = raw_value.strip()
        if not token:
            continue

        lower_token = token.lower()
        if lower_token.startswith("bearer "):
            return token

        # Some deployments configure the environment variable with the full
        # header value, e.g. ``Token <key>``. Treat any value that already
        # contains whitespace as a complete header and return it unchanged so
        # we do not accidentally prepend an additional prefix.
        if " " in token:
            return token

        return f"Bearer {token}"
    return ""


def _build_bdl_client() -> Optional[CachedBallDontLieAPI]:
    api_key = _get_bdl_api_key()
    if not api_key:
        logger.warning(
            "BALLDONTLIE_API_TOKEN environment variable is not configured; "
            "skipping BallDontLie sync."
        )
        return None
    with _BDL_CLIENT_LOCK:
        cached_client = _BDL_CLIENT_CACHE.get(api_key)
        if cached_client is not None:
            return cached_client

        client = build_cached_bdl_client(api_key=api_key)
        _BDL_CLIENT_CACHE[api_key] = client
        return client


def sync_teams() -> SyncResult:
    """Fetch the list of NBA teams from BallDontLie and persist them as Options."""
    client = _build_bdl_client()
    if client is None:
        return SyncResult()

    def _list_teams(per_page_value: Optional[int]) -> Any:
        kwargs = {}
        if per_page_value is not None:
            kwargs["per_page"] = per_page_value
        return client.nba.teams.list(**kwargs)

    try:
        response = _list_teams(100)
    except TypeError as exc:
        if "per_page" not in str(exc):
            raise
        logger.debug(
            "NBATeamsAPI.list does not accept per_page parameter; retrying without pagination. %s",
            exc,
        )
        try:
            response = _list_teams(None)
        except BallDontLieException:
            logger.exception("Unable to fetch team list from BallDontLie API.")
            return SyncResult()
    except BallDontLieException:
        logger.exception("Unable to fetch team list from BallDontLie API.")
        return SyncResult()

    created = 0
    updated = 0
    seen_ids: set[str] = set()

    teams_cat = NbaTeamManager.get_category()

    for team in getattr(response, "data", []) or []:
        team_id = getattr(team, "id", None)
        if not team_id:
            continue

        full_name = getattr(team, "full_name", "") or getattr(team, "name", "")
        abbreviation = getattr(team, "abbreviation", "") or ""
        city = getattr(team, "city", "") or ""
        conference = getattr(team, "conference", "") or ""
        division = getattr(team, "division", "") or ""

        if not (conference and division):
            continue

        name = full_name or city or abbreviation
        if not name:
            continue

        defaults = {
            "slug": abbreviation.lower() if abbreviation else name.lower().replace(" ", "-"),
            "name": name,
            "short_name": abbreviation,
            "description": f"{city} - {conference} Conference" if conference else city,
            "metadata": {
                "city": city,
                "conference": conference,
                "division": division,
            },
            "is_active": True,
            "sort_order": 0,
        }

        external_id = str(team_id)
        option, created_flag = Option.objects.update_or_create(
            category=teams_cat,
            external_id=external_id,
            defaults=defaults,
        )

        seen_ids.add(external_id)
        if created_flag:
            created += 1
        else:
            updated += 1

    # Remove teams that no longer exist
    removed = 0
    if seen_ids:
        query = Option.objects.filter(category=teams_cat)
        query = query.exclude(external_id__in=seen_ids)
        removed, _ = query.delete()

    return SyncResult(created=created, updated=updated, removed=removed)


def sync_players(throttle_seconds: float = PLAYER_SYNC_THROTTLE_SECONDS) -> SyncResult:
    """
    Fetch all active NBA players from BallDontLie and persist them as Options.

    The API is rate limited to five requests per minute. ``throttle_seconds``
    governs the sleep interval between subsequent requests to stay within that
    budget.
    """
    client = _build_bdl_client()
    if client is None:
        return SyncResult()

    seen_ids: set[str] = set()
    created = 0
    updated = 0
    processed = 0

    cursor: Optional[int] = None
    seen_cursors: set[Optional[int]] = set()

    players_cat = NbaPlayerManager.get_category()

    while True:
        params: dict[str, Any] = {"per_page": 100}
        if cursor is not None:
            params["cursor"] = cursor

        try:
            response = client.nba.players.list_active(**params)
        except BallDontLieException:
            logger.exception("Unable to fetch player list from BallDontLie API.")
            break

        for player in getattr(response, "data", []) or []:
            player_id = getattr(player, "id", None)
            if player_id is None:
                continue

            first_name = getattr(player, "first_name", "") or ""
            last_name = getattr(player, "last_name", "") or ""
            if not (first_name or last_name):
                continue

            display_name = f"{first_name} {last_name}".strip()
            position = getattr(player, "position", "") or ""

            team_obj = getattr(player, "team", None)
            team_abbr = getattr(team_obj, "abbreviation", "") if team_obj else ""
            team_name = getattr(team_obj, "full_name", "") or getattr(team_obj, "name", "") if team_obj else ""

            short_name = f"{first_name[0]}. {last_name}" if first_name else last_name
            description = f"{position} - {team_abbr}" if team_abbr else position

            defaults = {
                "slug": f"{first_name}-{last_name}".lower().replace(" ", "-"),
                "name": display_name,
                "short_name": short_name,
                "description": description,
                "metadata": {
                    "position": position,
                    "team_abbreviation": team_abbr,
                    "team_name": team_name,
                },
                "is_active": True,
                "sort_order": 0,
            }

            external_id = str(player_id)
            _, created_flag = Option.objects.update_or_create(
                category=players_cat,
                external_id=external_id,
                defaults=defaults,
            )

            if created_flag:
                created += 1
            else:
                updated += 1

            seen_ids.add(external_id)
            processed += 1

        meta = getattr(response, "meta", None)
        next_cursor = _extract_next_cursor(meta)
        if next_cursor is None or next_cursor in seen_cursors:
            break

        seen_cursors.add(next_cursor)
        cursor = next_cursor

        if throttle_seconds > 0:
            time.sleep(throttle_seconds)

    # Remove players that no longer exist
    removed = 0
    if processed:
        query = Option.objects.filter(category=players_cat)
        if seen_ids:
            query = query.exclude(external_id__in=seen_ids)
        removed, _ = query.delete()

    return SyncResult(created=created, updated=updated, removed=removed)


def _extract_next_cursor(meta: Any) -> Optional[int | str]:
    """Extract the next cursor from API response metadata."""
    if meta is None:
        return None

    next_cursor = getattr(meta, "next_cursor", None)
    if next_cursor is not None:
        return next_cursor

    if isinstance(meta, dict):
        if meta.get("next_cursor") is not None:
            return meta["next_cursor"]

        next_link: Optional[Any] = meta.get("next")
        if isinstance(meta.get("links"), dict):
            next_link = next_link or meta["links"].get("next")

        if isinstance(next_link, str) and next_link:
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(next_link)
            query = parse_qs(parsed.query)
            raw_cursor: Optional[str] = None
            for key in ("cursor", "page", "next_cursor"):
                values = query.get(key)
                if values:
                    raw_cursor = values[0]
                    break
            if raw_cursor is not None:
                try:
                    return int(raw_cursor)
                except (TypeError, ValueError):
                    return raw_cursor

        if meta.get("next_page") is not None:
            return meta["next_page"]

    return None


def fetch_upcoming_week_games(limit: int = 7) -> tuple[Optional[date], list[dict]]:
    """Fetch upcoming NBA games for the next week."""
    today = timezone.localdate()
    start_date = today + timedelta(days=1)
    # The NBA regular season can begin several weeks in the future. When the
    # current week has no games scheduled (e.g. in the offseason), expand the
    # search window so that we can surface the first available week of games in
    # the upcoming season.
    end_date = today + timedelta(days=30)

    client = _build_bdl_client()
    if client is None:
        return None, []

    try:
        response = client.nba.games.list(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            per_page=100,
            postseason="false",
        )
    except BallDontLieException:
        logger.exception("Unable to fetch games from BallDontLie API.")
        return None, []

    collected = []
    for game in response.data:
        status = (getattr(game, "status", "") or "").lower()
        if "final" in status:
            continue

        date_str = getattr(game, "date", "")
        if not date_str:
            continue

        try:
            game_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        home_team = getattr(game, "home_team", None)
        away_team = getattr(game, "visitor_team", None)

        collected.append(
            {
                "game_id": str(getattr(game, "id", "")),
                "game_time": timezone.make_aware(game_time)
                if timezone.is_naive(game_time)
                else game_time,
                "home_team": {
                    "id": getattr(home_team, "id", None),
                    "full_name": getattr(home_team, "full_name", ""),
                    "name": getattr(home_team, "name", ""),
                    "abbreviation": getattr(home_team, "abbreviation", ""),
                    "city": getattr(home_team, "city", ""),
                    "conference": getattr(home_team, "conference", ""),
                    "division": getattr(home_team, "division", ""),
                },
                "away_team": {
                    "id": getattr(away_team, "id", None),
                    "full_name": getattr(away_team, "full_name", ""),
                    "name": getattr(away_team, "name", ""),
                    "abbreviation": getattr(away_team, "abbreviation", ""),
                    "city": getattr(away_team, "city", ""),
                    "conference": getattr(away_team, "conference", ""),
                    "division": getattr(away_team, "division", ""),
                },
                "arena": getattr(game, "arena", "") or "",
            }
        )

    if not collected:
        return None, []

    earliest_game = min(collected, key=lambda item: item["game_time"])
    earliest_game_date = timezone.localdate(earliest_game["game_time"])

    initial_week_start = start_date
    if earliest_game_date >= (initial_week_start + timedelta(days=limit)):
        week_start = earliest_game_date
    else:
        week_start = initial_week_start

    days = max(1, limit)
    week_end = week_start + timedelta(days=days)

    games_in_window = [
        game
        for game in collected
        if week_start <= timezone.localdate(game["game_time"]) < week_end
    ]

    if not games_in_window:
        return week_start, []

    games_by_date: dict[date, list[dict]] = {}
    for game in games_in_window:
        slot_date = timezone.localdate(game["game_time"])
        games_by_date.setdefault(slot_date, []).append(game)

    # Select one game per day
    selected: list[dict] = []
    for offset in range(days):
        current_date = week_start + timedelta(days=offset)
        daily_games = games_by_date.get(current_date)
        if not daily_games:
            continue
        # Just pick the first game for simplicity
        chosen = sorted(
            daily_games,
            key=lambda item: (item["game_time"], item["game_id"]),
        )[0]
        selected.append(chosen)

    selected.sort(key=lambda item: item["game_time"])
    return week_start, selected
