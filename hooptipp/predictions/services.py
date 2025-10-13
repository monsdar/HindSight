import logging
import os
import threading
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

from balldontlie.exceptions import BallDontLieException
from django.utils import timezone

from .balldontlie_client import CachedBallDontLieAPI, build_cached_bdl_client
from .models import (
    NbaTeam,
    PredictionEvent,
    PredictionOption,
    ScheduledGame,
    TipType,
)


logger = logging.getLogger(__name__)


def _get_bdl_api_key() -> str:
    """Return the configured BallDontLie API token formatted for requests."""

    def _candidates() -> Iterable[str]:
        yield os.environ.get('BALLDONTLIE_API_TOKEN', '')
        yield os.environ.get('BALLDONTLIE_API_KEY', '')

    for raw_value in _candidates():
        token = raw_value.strip()
        if not token:
            continue
        if token.lower().startswith('bearer '):
            return token
        return f'Bearer {token}'
    return ''


_BDL_CLIENT_CACHE: Dict[str, CachedBallDontLieAPI] = {}
_BDL_CLIENT_LOCK = threading.Lock()


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
        choices.append((str(team_id), name))

    choices.sort(key=lambda item: item[1])
    return choices


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
            next_cursor = getattr(meta, 'next_cursor', None)
            if next_cursor is None or next_cursor in seen_cursors:
                break

            seen_cursors.add(next_cursor)
            cursor = next_cursor
    except BallDontLieException:
        logger.exception('Unable to fetch player list from BallDontLie API.')
        return []

    choices.sort(key=lambda item: item[1])
    return choices


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
        return team

    abbreviation = defaults['abbreviation']
    candidates = NbaTeam.objects.all()
    if abbreviation:
        team = candidates.filter(abbreviation__iexact=abbreviation).first()
        if team:
            for field, value in defaults.items():
                setattr(team, field, value)
            team.save()
            return team

    team = candidates.filter(name__iexact=name).first()
    if team:
        for field, value in defaults.items():
            setattr(team, field, value)
        team.save()
        return team

    team = NbaTeam.objects.create(**defaults)
    return team


def _update_event_options(
    event: PredictionEvent,
    home_team: Optional[NbaTeam],
    away_team: Optional[NbaTeam],
) -> None:
    if home_team:
        PredictionOption.objects.update_or_create(
            event=event,
            team=home_team,
            defaults={
                'label': home_team.name,
                'sort_order': 2,
                'is_active': True,
            },
        )
    if away_team:
        PredictionOption.objects.update_or_create(
            event=event,
            team=away_team,
            defaults={
                'label': away_team.name,
                'sort_order': 1,
                'is_active': True,
            },
        )

    (PredictionOption.objects
        .filter(event=event)
        .exclude(team__in=[team for team in [home_team, away_team] if team])
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
        event, _ = PredictionEvent.objects.update_or_create(
            scheduled_game=manual,
            defaults=manual_defaults,
        )
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
        event, _ = PredictionEvent.objects.update_or_create(
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
