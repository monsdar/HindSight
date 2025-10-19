import logging
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import parse_qs, urlparse

from balldontlie.exceptions import BallDontLieException
from django.utils import timezone

from hooptipp.nba.client import CachedBallDontLieAPI, build_cached_bdl_client
from hooptipp.nba.models import ScheduledGame
from .models import (
    PredictionEvent,
    TipType,
)


logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Base summary of a BallDontLie synchronisation run."""

    created: int = 0
    updated: int = 0
    removed: int = 0

    @property
    def changed(self) -> bool:
        """Return ``True`` when the sync modified the database."""

        return any((self.created, self.updated, self.removed))


def _get_bdl_api_key() -> str:
    """Return the configured BallDontLie API token formatted for requests."""

    def _candidates() -> Iterable[str]:
        yield os.environ.get('BALLDONTLIE_API_TOKEN', '')
        yield os.environ.get('BALLDONTLIE_API_KEY', '')

    for raw_value in _candidates():
        token = raw_value.strip()
        if not token:
            continue

        lower_token = token.lower()
        if lower_token.startswith('bearer '):
            return token

        # Some deployments configure the environment variable with the full
        # header value, e.g. ``Token <key>``. Treat any value that already
        # contains whitespace as a complete header and return it unchanged so
        # we do not accidentally prepend an additional prefix.
        if ' ' in token:
            return token

        return f'Bearer {token}'
    return ''


_BDL_CLIENT_CACHE: Dict[str, CachedBallDontLieAPI] = {}
_BDL_CLIENT_LOCK = threading.Lock()

CursorType = Union[int, str]


def _build_bdl_client() -> Optional[CachedBallDontLieAPI]:
    api_key = _get_bdl_api_key()
    if not api_key:
        logger.warning('BALLDONTLIE_API_TOKEN environment variable is not configured; '
                       'skipping BallDontLie sync.')
        return None
    with _BDL_CLIENT_LOCK:
        cached_client = _BDL_CLIENT_CACHE.get(api_key)
        if cached_client is not None:
            return cached_client

        client = build_cached_bdl_client(api_key=api_key)
        _BDL_CLIENT_CACHE[api_key] = client
        return client


class GameWeightCalculator:
    """Compute weights for candidate NBA games."""

    def get_weight(self, game: dict) -> float:
        """Return the selection weight for ``game``."""

        return 1.0


def _serialise_team(team_obj: Any) -> Optional[dict]:
    if not team_obj:
        return None
    return {
        'id': getattr(team_obj, 'id', None),
        'name': getattr(team_obj, 'name', ''),
        'full_name': getattr(team_obj, 'full_name', ''),
        'abbreviation': getattr(team_obj, 'abbreviation', ''),
        'city': getattr(team_obj, 'city', ''),
        'conference': getattr(team_obj, 'conference', ''),
        'division': getattr(team_obj, 'division', ''),
    }


def _extract_next_cursor(meta: Any) -> Optional[CursorType]:
    if meta is None:
        return None

    next_cursor = getattr(meta, 'next_cursor', None)
    if next_cursor is not None:
        return next_cursor

    next_url = getattr(meta, 'next', '')
    if not next_url:
        return None

    parsed = urlparse(next_url)
    query_params = parse_qs(parsed.query)
    cursor_values = query_params.get('cursor', [])
    return cursor_values[0] if cursor_values else None


def fetch_upcoming_week_games(limit: int = 7) -> Tuple[Optional[date], List[dict]]:
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
        )
    except BallDontLieException:
        logger.exception('Unable to fetch upcoming games from BallDontLie API.')
        return None, []

    collected: List[dict] = []
    for game in getattr(response, 'data', []):
        status = (getattr(game, 'status', '') or '').lower()
        if 'final' in status:
            continue

        datetime_str = getattr(game, 'datetime', '')
        if not datetime_str:
            continue

        try:
            game_time = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            if timezone.is_naive(game_time):
                game_time = timezone.make_aware(game_time)
        except ValueError:
            continue

        if game_time < timezone.now():
            continue

        home_team = getattr(game, 'home_team', None)
        away_team = getattr(game, 'visitor_team', None)

        collected.append({
            'game_id': str(getattr(game, 'id', '')),
            'game_time': game_time,
            'home_team': _serialise_team(home_team) or {},
            'away_team': _serialise_team(away_team) or {},
            'arena': getattr(game, 'arena', '') or '',
        })

    if not collected:
        return None, []

    earliest_game = min(collected, key=lambda item: item['game_time'])
    earliest_game_date = timezone.localdate(earliest_game['game_time'])

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
        if week_start <= timezone.localdate(game['game_time']) < week_end
    ]

    if not games_in_window:
        return week_start, []

    games_by_date: Dict[date, List[dict]] = {}
    for game in games_in_window:
        slot_date = timezone.localdate(game['game_time'])
        games_by_date.setdefault(slot_date, []).append(game)

    calculator = GameWeightCalculator()
    selected: List[dict] = []
    for offset in range(days):
        current_date = week_start + timedelta(days=offset)
        daily_games = games_by_date.get(current_date)
        if not daily_games:
            continue
        chosen = sorted(
            daily_games,
            key=lambda item: (
                -calculator.get_weight(item),
                item['game_time'],
                item['game_id'],
            ),
        )[0]
        selected.append(chosen)

    selected.sort(key=lambda item: item['game_time'])
    return week_start, selected


def sync_weekly_games_via_source(limit: int = 7) -> Tuple[Optional[TipType], List[PredictionEvent], Optional[date]]:
    """
    Sync weekly games using the NBA event source.
    
    This is the recommended way to sync games using the event source system.
    """
    from .event_sources import get_source
    
    try:
        nba_source = get_source('nba-balldontlie')
        if nba_source.is_configured():
            nba_source.sync_options()  # Sync teams/players first
            nba_source.sync_events(limit=limit)  # Then sync events
    except Exception:
        logger.exception("Failed to sync via NBA event source")
    
    # Return current state
    tip_type = TipType.objects.filter(slug='weekly-games').first()
    if not tip_type:
        return None, [], None
    
    events = list(
        PredictionEvent.objects.filter(
            tip_type=tip_type,
            is_active=True,
        ).order_by('deadline', 'sort_order')
    )
    
    week_start = None
    if events:
        earliest = events[0].deadline
        week_start = timezone.localdate(earliest)
        if tip_type.deadline != earliest:
            TipType.objects.filter(pk=tip_type.pk).update(deadline=earliest)
            tip_type.deadline = earliest
    
    return tip_type, events, week_start
