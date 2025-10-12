import random
from datetime import datetime, timedelta
from typing import List, Tuple

from django.utils import timezone

from nba_api.live.nba.endpoints import scoreboard

from .models import ScheduledGame, TipType


def fetch_upcoming_week_games(limit: int = 5) -> List[dict]:
    today = timezone.now().date()
    collected = []

    for day_offset in range(1, 8):
        game_date = today + timedelta(days=day_offset)
        try:
            board = scoreboard.ScoreBoard(game_date=game_date.strftime('%Y-%m-%d'))
        except Exception:
            continue

        games_payload = board.games.get_dict().get('games', [])
        for game in games_payload:
            game_time = datetime.fromisoformat(game['gameTimeUTC'].replace('Z', '+00:00'))
            collected.append(
                {
                    'game_id': game['gameId'],
                    'game_time': timezone.make_aware(game_time) if timezone.is_naive(game_time) else game_time,
                    'home_team_name': f"{game['homeTeam']['teamCity']} {game['homeTeam']['teamName']}",
                    'home_team_tricode': game['homeTeam']['teamTricode'],
                    'away_team_name': f"{game['awayTeam']['teamCity']} {game['awayTeam']['teamName']}",
                    'away_team_tricode': game['awayTeam']['teamTricode'],
                    'arena': game.get('arenaName', ''),
                }
            )

    if not collected:
        return []

    random.shuffle(collected)
    return collected[:limit]


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
