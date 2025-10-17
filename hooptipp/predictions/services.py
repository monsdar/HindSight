import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import parse_qs, urlparse

from balldontlie.exceptions import BallDontLieException
from django.utils import timezone

from .balldontlie_client import CachedBallDontLieAPI, build_cached_bdl_client
from .models import (
    NbaPlayer,
    NbaTeam,
    PredictionEvent,
    PredictionOption,
    ScheduledGame,
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


class PlayerSyncResult(SyncResult):
    """Summary of a BallDontLie active player synchronisation run."""


class TeamSyncResult(SyncResult):
    """Summary of a BallDontLie NBA team synchronisation run."""


# The BallDontLie free tier allows 5 requests per minute. A throttle of 12.5
# seconds leaves a small safety margin between requests.
PLAYER_SYNC_THROTTLE_SECONDS = 12.5


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


@lru_cache
def get_team_choices() -> List[Tuple[str, str]]:
    """Return cached BallDontLie NBA team choices for dropdowns."""

    client = _build_bdl_client()
    if client is None:
        return []

    def _list_teams(per_page_value: Optional[int]) -> Any:
        kwargs = {}
        if per_page_value is not None:
            kwargs['per_page'] = per_page_value
        return client.nba.teams.list(**kwargs)

    try:
        response = _list_teams(100)
    except TypeError as exc:
        if "per_page" not in str(exc):
            raise
        logger.debug('NBATeamsAPI.list does not accept per_page parameter; retrying without pagination. %s', exc)
        try:
            response = _list_teams(None)
        except BallDontLieException:
            logger.exception('Unable to fetch team list from BallDontLie API.')
            return []
    except BallDontLieException:
        logger.exception('Unable to fetch team list from BallDontLie API.')
        return []

    choices: List[Tuple[str, str]] = []
    for team in getattr(response, 'data', []):
        team_id = getattr(team, 'id', None)
        if not team_id:
            continue
        name = getattr(team, 'full_name', '') or getattr(team, 'name', '')
        if not name:
            continue
        conference = getattr(team, 'conference', '') or ''
        division = getattr(team, 'division', '') or ''
        if not (conference and division):
            continue
        choices.append((str(team_id), name))

    choices.sort(key=lambda item: item[1])
    return choices


def sync_teams() -> TeamSyncResult:
    """Fetch the list of NBA teams from BallDontLie and persist them."""

    client = _build_bdl_client()
    if client is None:
        return TeamSyncResult()

    def _list_teams(per_page_value: Optional[int]) -> Any:
        kwargs = {}
        if per_page_value is not None:
            kwargs['per_page'] = per_page_value
        return client.nba.teams.list(**kwargs)

    try:
        response = _list_teams(100)
    except TypeError as exc:
        if "per_page" not in str(exc):
            raise
        logger.debug('NBATeamsAPI.list does not accept per_page parameter; retrying without pagination. %s', exc)
        try:
            response = _list_teams(None)
        except BallDontLieException:
            logger.exception('Unable to fetch team list from BallDontLie API.')
            return TeamSyncResult()
    except BallDontLieException:
        logger.exception('Unable to fetch team list from BallDontLie API.')
        return TeamSyncResult()

    created = 0
    updated = 0
    seen_ids: set[int] = set()

    for team in getattr(response, 'data', []) or []:
        team_data = _serialise_team(team)
        if not team_data:
            continue

        team_id = team_data.get('id')
        if team_id is None:
            continue

        defaults = {
            'name': team_data.get('full_name') or team_data.get('name') or '',
            'abbreviation': team_data.get('abbreviation') or '',
            'city': team_data.get('city') or '',
            'conference': team_data.get('conference') or '',
            'division': team_data.get('division') or '',
        }

        if not (defaults['conference'] and defaults['division']):
            continue

        name = defaults['name'] or defaults['city'] or defaults['abbreviation']
        if not name:
            continue
        defaults['name'] = name

        balldontlie_id = int(team_id)

        team_obj = NbaTeam.objects.filter(balldontlie_id=balldontlie_id).first()
        created_flag = False
        if team_obj is None:
            abbreviation = defaults['abbreviation']
            candidate = None
            if abbreviation:
                candidate = NbaTeam.objects.filter(abbreviation__iexact=abbreviation).first()
            if candidate is None and name:
                candidate = NbaTeam.objects.filter(name__iexact=name).first()

            if candidate is None:
                team_obj = NbaTeam(balldontlie_id=balldontlie_id)
                created_flag = True
            else:
                team_obj = candidate

        team_obj.name = defaults['name']
        team_obj.abbreviation = defaults['abbreviation']
        team_obj.city = defaults['city']
        team_obj.conference = defaults['conference']
        team_obj.division = defaults['division']
        team_obj.balldontlie_id = balldontlie_id
        team_obj.save()

        seen_ids.add(balldontlie_id)
        if created_flag:
            created += 1
        else:
            updated += 1

    removed = 0
    if seen_ids:
        query = NbaTeam.objects.filter(balldontlie_id__isnull=False)
        query = query.exclude(balldontlie_id__in=seen_ids)
        removed, _ = query.delete()

    get_team_choices.cache_clear()

    return TeamSyncResult(created=created, updated=updated, removed=removed)


@lru_cache
def get_player_choices() -> List[Tuple[str, str]]:
    """Return cached BallDontLie NBA player choices for dropdowns."""

    client = _build_bdl_client()
    if client is None:
        return []

    choices: List[Tuple[str, str]] = []
    cursor: Optional[int] = None
    seen_cursors: set[Optional[int]] = set()

    try:
        while True:
            params = {'per_page': 100}
            if cursor is not None:
                params['cursor'] = cursor

            response = client.nba.players.list_active(**params)

            for player in getattr(response, 'data', []):
                player_id = getattr(player, 'id', None)
                if not player_id:
                    continue
                first_name = getattr(player, 'first_name', '')
                last_name = getattr(player, 'last_name', '')
                if not (first_name or last_name):
                    continue
                name = f"{first_name} {last_name}".strip()
                team = getattr(getattr(player, 'team', None), 'abbreviation', '')
                if team:
                    name = f"{name} ({team})"
                choices.append((str(player_id), name))

            meta = getattr(response, 'meta', None)
            next_cursor = _extract_next_cursor(meta)
            if next_cursor is None or next_cursor in seen_cursors:
                break

            seen_cursors.add(next_cursor)
            cursor = next_cursor
    except BallDontLieException:
        logger.exception('Unable to fetch player list from BallDontLie API.')
        return []

    choices.sort(key=lambda item: item[1])
    return choices


def _serialise_team(team_obj: Any) -> Optional[dict]:
    if team_obj is None:
        return None

    return {
        'id': getattr(team_obj, 'id', None),
        'full_name': getattr(team_obj, 'full_name', ''),
        'name': getattr(team_obj, 'name', ''),
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

    if isinstance(meta, dict):
        if meta.get('next_cursor') is not None:
            return meta['next_cursor']

        next_link: Optional[Any] = meta.get('next')
        if isinstance(meta.get('links'), dict):
            next_link = next_link or meta['links'].get('next')

        if isinstance(next_link, str) and next_link:
            parsed = urlparse(next_link)
            query = parse_qs(parsed.query)
            raw_cursor: Optional[str] = None
            for key in ('cursor', 'page', 'next_cursor'):
                values = query.get(key)
                if values:
                    raw_cursor = values[0]
                    break
            if raw_cursor is not None:
                try:
                    return int(raw_cursor)
                except (TypeError, ValueError):
                    return raw_cursor

        if meta.get('next_page') is not None:
            return meta['next_page']

    return None


def sync_active_players(throttle_seconds: float = PLAYER_SYNC_THROTTLE_SECONDS) -> PlayerSyncResult:
    """Fetch all active NBA players from BallDontLie and persist them.

    The API is rate limited to five requests per minute. ``throttle_seconds``
    governs the sleep interval between subsequent requests to stay within that
    budget. The function returns a :class:`PlayerSyncResult` with the outcome of
    the sync operation.
    """

    client = _build_bdl_client()
    if client is None:
        return PlayerSyncResult()

    seen_ids: set[int] = set()
    created = 0
    updated = 0
    processed = 0

    cursor: Optional[int] = None
    seen_cursors: set[Optional[int]] = set()

    while True:
        params: Dict[str, Any] = {'per_page': 100}
        if cursor is not None:
            params['cursor'] = cursor

        try:
            response = client.nba.players.list_active(**params)
        except BallDontLieException:
            logger.exception('Unable to fetch player list from BallDontLie API.')
            break

        for player in getattr(response, 'data', []) or []:
            player_id = getattr(player, 'id', None)
            if player_id is None:
                continue

            first_name = getattr(player, 'first_name', '') or ''
            last_name = getattr(player, 'last_name', '') or ''
            if not (first_name or last_name):
                continue

            display_name = f"{first_name} {last_name}".strip()
            position = getattr(player, 'position', '') or ''

            team_data = _serialise_team(getattr(player, 'team', None))
            team: Optional[NbaTeam] = None
            if team_data:
                team = _upsert_team(team_data)

            defaults = {
                'first_name': first_name,
                'last_name': last_name,
                'display_name': display_name,
                'position': position,
                'team': team,
            }

            _, created_flag = NbaPlayer.objects.update_or_create(
                balldontlie_id=int(player_id),
                defaults=defaults,
            )
            if created_flag:
                created += 1
            else:
                updated += 1

            seen_ids.add(int(player_id))
            processed += 1

        meta = getattr(response, 'meta', None)
        next_cursor = _extract_next_cursor(meta)
        if next_cursor is None or next_cursor in seen_cursors:
            break

        seen_cursors.add(next_cursor)
        cursor = next_cursor

        if throttle_seconds > 0:
            time.sleep(throttle_seconds)

    removed = 0
    if processed:
        query = NbaPlayer.objects.filter(balldontlie_id__isnull=False)
        if seen_ids:
            query = query.exclude(balldontlie_id__in=seen_ids)
        removed, _ = query.delete()

    return PlayerSyncResult(created=created, updated=updated, removed=removed)


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
            postseason='false',
        )
    except BallDontLieException:
        logger.exception('Unable to fetch games from BallDontLie API.')
        return None, []

    collected = []
    for game in response.data:
        status = (getattr(game, 'status', '') or '').lower()
        if 'final' in status:
            continue

        date_str = getattr(game, 'date', '')
        if not date_str:
            continue

        try:
            game_time = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except ValueError:
            continue

        home_team = getattr(game, 'home_team', None)
        away_team = getattr(game, 'visitor_team', None)

        collected.append(
            {
                'game_id': str(getattr(game, 'id', '')),
                'game_time': timezone.make_aware(game_time) if timezone.is_naive(game_time) else game_time,
                'home_team': {
                    'id': getattr(home_team, 'id', None),
                    'full_name': getattr(home_team, 'full_name', ''),
                    'name': getattr(home_team, 'name', ''),
                    'abbreviation': getattr(home_team, 'abbreviation', ''),
                    'city': getattr(home_team, 'city', ''),
                    'conference': getattr(home_team, 'conference', ''),
                    'division': getattr(home_team, 'division', ''),
                },
                'away_team': {
                    'id': getattr(away_team, 'id', None),
                    'full_name': getattr(away_team, 'full_name', ''),
                    'name': getattr(away_team, 'name', ''),
                    'abbreviation': getattr(away_team, 'abbreviation', ''),
                    'city': getattr(away_team, 'city', ''),
                    'conference': getattr(away_team, 'conference', ''),
                    'division': getattr(away_team, 'division', ''),
                },
                'arena': getattr(game, 'arena', '') or '',
            }
        )

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


def _upsert_team(team_data: dict) -> Optional[NbaTeam]:
    from .models import Option, OptionCategory
    
    team_id = team_data.get('id')

    defaults = {
        'name': team_data.get('full_name') or team_data.get('name') or '',
        'abbreviation': team_data.get('abbreviation') or '',
        'city': team_data.get('city') or '',
        'conference': team_data.get('conference') or '',
        'division': team_data.get('division') or '',
    }

    name = defaults['name'] or defaults['city'] or defaults['abbreviation']
    if not name:
        return None
    defaults['name'] = name

    if team_id:
        team, _ = NbaTeam.objects.update_or_create(
            balldontlie_id=int(team_id),
            defaults=defaults,
        )
    else:
        abbreviation = defaults['abbreviation']
        candidates = NbaTeam.objects.all()
        if abbreviation:
            team = candidates.filter(abbreviation__iexact=abbreviation).first()
            if team:
                for field, value in defaults.items():
                    setattr(team, field, value)
                team.save()
            else:
                team = NbaTeam.objects.create(**defaults)
        else:
            team = candidates.filter(name__iexact=name).first()
            if team:
                for field, value in defaults.items():
                    setattr(team, field, value)
                team.save()
            else:
                team = NbaTeam.objects.create(**defaults)
    
    # Also create/update the generic Option for this team
    teams_cat, _ = OptionCategory.objects.get_or_create(
        slug='nba-teams',
        defaults={'name': 'NBA Teams', 'icon': 'basketball'}
    )
    
    Option.objects.update_or_create(
        category=teams_cat,
        metadata__nba_team_id=team.id,
        defaults={
            'slug': (defaults['abbreviation'] or name).lower().replace(' ', '-'),
            'name': name,
            'short_name': defaults['abbreviation'],
            'description': f"{defaults['city']} - {defaults['conference']} Conference" if defaults['conference'] else defaults['city'],
            'metadata': {
                'nba_team_id': team.id,
                'city': defaults['city'],
                'conference': defaults['conference'],
                'division': defaults['division'],
            },
            'external_id': str(team_id) if team_id else '',
            'is_active': True,
        }
    )
    
    return team


def _ensure_event_points(event: PredictionEvent, tip_type: TipType, *, created: bool) -> None:
    if created and event.points != tip_type.default_points:
        event.points = tip_type.default_points
        event.save(update_fields=['points'])


def _update_event_options(
    event: PredictionEvent,
    home_team: Optional[NbaTeam],
    away_team: Optional[NbaTeam],
) -> None:
    from .models import Option, OptionCategory
    
    teams_cat = OptionCategory.objects.filter(slug='nba-teams').first()
    if not teams_cat:
        return
    
    valid_options = []
    
    if home_team:
        home_option = Option.objects.filter(
            category=teams_cat,
            metadata__nba_team_id=home_team.id
        ).first()
        if home_option:
            PredictionOption.objects.update_or_create(
                event=event,
                option=home_option,
                defaults={
                    'label': home_option.name,
                    'sort_order': 2,
                    'is_active': True,
                },
            )
            valid_options.append(home_option)
    
    if away_team:
        away_option = Option.objects.filter(
            category=teams_cat,
            metadata__nba_team_id=away_team.id
        ).first()
        if away_option:
            PredictionOption.objects.update_or_create(
                event=event,
                option=away_option,
                defaults={
                    'label': away_option.name,
                    'sort_order': 1,
                    'is_active': True,
                },
            )
            valid_options.append(away_option)

    if valid_options:
        (PredictionOption.objects
            .filter(event=event)
            .exclude(option__in=valid_options)
            .delete())


def _ensure_manual_events(
    tip_type: TipType,
    now: datetime,
    starting_order: int = 1,
) -> List[int]:
    manual_games = (
        ScheduledGame.objects
        .filter(tip_type=tip_type, is_manual=True)
        .order_by('game_date')
    )
    event_ids: List[int] = []

    for index, manual in enumerate(manual_games, start=starting_order):
        manual_opens = min(now, manual.game_date)
        manual_defaults = {
            'tip_type': tip_type,
            'name': f"{manual.away_team_tricode} @ {manual.home_team_tricode}".strip(),
            'description': f"{manual.away_team} at {manual.home_team}",
            'target_kind': PredictionEvent.TargetKind.TEAM,
            'selection_mode': PredictionEvent.SelectionMode.CURATED,
            'opens_at': manual_opens,
            'deadline': manual.game_date,
            'reveal_at': manual_opens,
            'is_active': True,
            'sort_order': index,
        }
        event, created = PredictionEvent.objects.update_or_create(
            scheduled_game=manual,
            defaults=manual_defaults,
        )
        _ensure_event_points(event, tip_type, created=created)
        event_ids.append(event.id)

        home_team_data = {
            'id': None,
            'full_name': manual.home_team,
            'name': manual.home_team,
            'abbreviation': manual.home_team_tricode,
            'city': '',
            'conference': '',
            'division': '',
        }
        away_team_data = {
            'id': None,
            'full_name': manual.away_team,
            'name': manual.away_team,
            'abbreviation': manual.away_team_tricode,
            'city': '',
            'conference': '',
            'division': '',
        }

        home_team = _upsert_team(home_team_data)
        away_team = _upsert_team(away_team_data)
        _update_event_options(event, home_team, away_team)

    return event_ids


def sync_weekly_games_via_source(limit: int = 7) -> Tuple[Optional[TipType], List[PredictionEvent], Optional[date]]:
    """
    Sync weekly games using the NBA event source.
    
    This is the new recommended way to sync games using the event source system.
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


def sync_weekly_games(limit: int = 7) -> Tuple[Optional[TipType], List[PredictionEvent], Optional[date]]:
    week_start, games = fetch_upcoming_week_games(limit=limit)
    if not games:
        tip_type = TipType.objects.filter(slug='weekly-games').first()
        if tip_type is None:
            return None, [], week_start

        now = timezone.now()
        _ensure_manual_events(tip_type, now)

        events = list(
            PredictionEvent.objects.filter(
                tip_type=tip_type,
                is_active=True,
            ).order_by('deadline', 'sort_order')
        )

        if events:
            earliest = events[0].deadline
            if tip_type.deadline != earliest:
                TipType.objects.filter(pk=tip_type.pk).update(deadline=earliest)
                tip_type.deadline = earliest
        return tip_type, events, week_start

    earliest_game_time = min(game['game_time'] for game in games)

    tip_type, _ = TipType.objects.update_or_create(
        slug='weekly-games',
        defaults={
            'name': 'Weekly games',
            'description': 'Featured matchups for the upcoming week',
            'category': TipType.TipCategory.GAME,
            'deadline': earliest_game_time,
            'is_active': True,
        },
    )

    now = timezone.now()
    selected_ids = []
    event_ids = []
    for sort_index, game in enumerate(games, start=1):
        scheduled, _ = ScheduledGame.objects.update_or_create(
            nba_game_id=game['game_id'],
            defaults={
                'tip_type': tip_type,
                'game_date': game['game_time'],
                'home_team': game['home_team']['full_name'] or game['home_team']['name'],
                'home_team_tricode': game['home_team']['abbreviation'],
                'away_team': game['away_team']['full_name'] or game['away_team']['name'],
                'away_team_tricode': game['away_team']['abbreviation'],
                'venue': game['arena'],
                'is_manual': False,
            },
        )
        selected_ids.append(scheduled.nba_game_id)

        home_team = _upsert_team(game['home_team'])
        away_team = _upsert_team(game['away_team'])

        opens_at = min(now, game['game_time'])
        event, created = PredictionEvent.objects.update_or_create(
            scheduled_game=scheduled,
            defaults={
                'tip_type': tip_type,
                'name': f"{game['away_team']['abbreviation']} @ {game['home_team']['abbreviation']}",
                'description': (
                    f"{game['away_team']['full_name']} at {game['home_team']['full_name']}"
                ),
                'target_kind': PredictionEvent.TargetKind.TEAM,
                'selection_mode': PredictionEvent.SelectionMode.CURATED,
                'opens_at': opens_at,
                'deadline': game['game_time'],
                'reveal_at': opens_at,
                'is_active': True,
                'sort_order': sort_index,
            },
        )
        _ensure_event_points(event, tip_type, created=created)
        event_ids.append(event.id)
        _update_event_options(event, home_team, away_team)

    (ScheduledGame.objects
        .filter(tip_type=tip_type, is_manual=False)
        .exclude(nba_game_id__in=selected_ids)
        .delete())

    event_ids.extend(_ensure_manual_events(tip_type, now, starting_order=len(event_ids) + 1))

    (PredictionEvent.objects
        .filter(tip_type=tip_type, scheduled_game__isnull=False)
        .exclude(id__in=event_ids)
        .delete())

    events = list(
        PredictionEvent.objects.filter(tip_type=tip_type).order_by('deadline', 'sort_order')
    )

    if events:
        earliest = events[0].deadline
        if tip_type.deadline != earliest:
            TipType.objects.filter(pk=tip_type.pk).update(deadline=earliest)
            tip_type.deadline = earliest

    return tip_type, events, week_start
