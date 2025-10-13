import logging
import os
import random
import threading
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from balldontlie.exceptions import BallDontLieException
from django.utils import timezone

from .balldontlie_client import CachedBallDontLieAPI, build_cached_bdl_client
from .models import ScheduledGame, TipType


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


def fetch_upcoming_week_games(limit: int = 5) -> List[dict]:
    today = timezone.now().date()
    start_date = today + timedelta(days=1)
    # The NBA regular season can begin several weeks in the future. When the
    # current week has no games scheduled (e.g. in the offseason), expand the
    # search window so that we can surface the first available week of games in
    # the upcoming season.
    end_date = today + timedelta(days=30)

    client = _build_bdl_client()
    if client is None:
        return []

    try:
        response = client.nba.games.list(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            per_page=100,
            postseason='false',
        )
    except BallDontLieException:
        logger.exception('Unable to fetch games from BallDontLie API.')
        return []

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

        collected.append(
            {
                'game_id': str(getattr(game, 'id', '')),
                'game_time': timezone.make_aware(game_time) if timezone.is_naive(game_time) else game_time,
                'home_team_name': getattr(getattr(game, 'home_team', None), 'full_name', ''),
                'home_team_tricode': getattr(getattr(game, 'home_team', None), 'abbreviation', ''),
                'away_team_name': getattr(getattr(game, 'visitor_team', None), 'full_name', ''),
                'away_team_tricode': getattr(getattr(game, 'visitor_team', None), 'abbreviation', ''),
                'arena': getattr(game, 'arena', '') or '',
            }
        )

    if not collected:
        return []

    earliest_game = min(collected, key=lambda item: item['game_time'])
    first_week_end = earliest_game['game_time'] + timedelta(days=7)
    first_week_games = [
        game for game in collected
        if earliest_game['game_time'] <= game['game_time'] < first_week_end
    ]

    random.shuffle(first_week_games)
    return first_week_games[:limit]


def sync_weekly_games(limit: int = 5) -> Tuple[TipType, List[ScheduledGame]]:
    games = fetch_upcoming_week_games(limit=limit)
    if not games:
        return None, []

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

    selected_ids = []
    for game in games:
        scheduled, _ = ScheduledGame.objects.update_or_create(
            nba_game_id=game['game_id'],
            defaults={
                'tip_type': tip_type,
                'game_date': game['game_time'],
                'home_team': game['home_team_name'],
                'home_team_tricode': game['home_team_tricode'],
                'away_team': game['away_team_name'],
                'away_team_tricode': game['away_team_tricode'],
                'venue': game['arena'],
            },
        )
        selected_ids.append(scheduled.nba_game_id)

    ScheduledGame.objects.filter(tip_type=tip_type).exclude(nba_game_id__in=selected_ids).delete()

    return tip_type, list(ScheduledGame.objects.filter(tip_type=tip_type).order_by('game_date'))
