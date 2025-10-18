"""
NBA event source using the BallDontLie API.

This source provides NBA teams, players, and weekly game predictions.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

from django.utils import timezone

from hooptipp.predictions.event_sources.base import EventSource, EventSourceResult
from hooptipp.predictions.models import (
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
)
from .models import ScheduledGame

from .managers import NbaPlayerManager, NbaTeamManager

logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    """Get the BallDontLie API key from environment."""
    for var_name in ["BALLDONTLIE_API_TOKEN", "BALLDONTLIE_API_KEY"]:
        key = os.environ.get(var_name, "").strip()
        if key:
            return key
    return ""


class NbaEventSource(EventSource):
    """Event source for NBA games and predictions via BallDontLie API."""

    @property
    def source_id(self) -> str:
        return "nba-balldontlie"

    @property
    def source_name(self) -> str:
        return "NBA (BallDontLie API)"

    @property
    def category_slugs(self) -> list[str]:
        return ["nba-teams", "nba-players"]

    def is_configured(self) -> bool:
        return bool(_get_api_key())

    def get_configuration_help(self) -> str:
        if self.is_configured():
            return "NBA source is configured and ready to use."
        return (
            "To configure the NBA source, set the BALLDONTLIE_API_TOKEN "
            "environment variable with your BallDontLie API key. "
            "Get an API key at: https://balldontlie.io"
        )

    def sync_options(self) -> EventSourceResult:
        """
        Sync NBA teams and players from BallDontLie API.

        This creates/updates Options for teams and players.
        """
        result = EventSourceResult()

        if not self.is_configured():
            result.add_error("NBA source is not configured (missing API key)")
            return result

        # Ensure categories exist
        NbaTeamManager.get_category()
        NbaPlayerManager.get_category()

        # Sync teams and players using services
        try:
            from .services import sync_teams, sync_players

            team_result = sync_teams()
            result.options_created += team_result.created
            result.options_updated += team_result.updated
            result.options_removed += team_result.removed

            player_result = sync_players()
            result.options_created += player_result.created
            result.options_updated += player_result.updated
            result.options_removed += player_result.removed

        except Exception as e:
            logger.exception(f"Error syncing NBA options: {e}")
            result.add_error(f"Failed to sync NBA options: {str(e)}")

        return result

    def sync_events(self, limit: int = 7) -> EventSourceResult:
        """
        Sync upcoming NBA games as prediction events.

        Args:
            limit: Number of days to look ahead for games.

        Returns:
            EventSourceResult with counts of events synced.
        """
        result = EventSourceResult()

        if not self.is_configured():
            result.add_error("NBA source is not configured (missing API key)")
            return result

        try:
            from .services import fetch_upcoming_week_games

            week_start, games = fetch_upcoming_week_games(limit=limit)

            if not games:
                # Check for manual games
                tip_type = TipType.objects.filter(slug="weekly-games").first()
                if tip_type:
                    manual_games = ScheduledGame.objects.filter(
                        tip_type=tip_type, is_manual=True
                    )
                    if manual_games.exists():
                        logger.info(
                            f"No API games found, but {manual_games.count()} manual games exist"
                        )
                return result

            # Get or create tip type
            earliest_game_time = min(game["game_time"] for game in games)
            tip_type, _ = TipType.objects.update_or_create(
                slug="weekly-games",
                defaults={
                    "name": "Weekly games",
                    "description": "Featured NBA matchups for the upcoming week",
                    "category": TipType.TipCategory.GAME,
                    "deadline": earliest_game_time,
                    "is_active": True,
                },
            )

            now = timezone.now()
            selected_ids = []
            event_ids = []

            teams_cat = NbaTeamManager.get_category()

            for sort_index, game in enumerate(games, start=1):
                # Find or create team options
                home_option = Option.objects.filter(
                    category=teams_cat,
                    short_name=game["home_team"]["abbreviation"],
                ).first()

                away_option = Option.objects.filter(
                    category=teams_cat,
                    short_name=game["away_team"]["abbreviation"],
                ).first()

                # Create ScheduledGame
                scheduled, created = ScheduledGame.objects.update_or_create(
                    nba_game_id=game["game_id"],
                    defaults={
                        "tip_type": tip_type,
                        "game_date": game["game_time"],
                        "home_team": game["home_team"]["full_name"]
                        or game["home_team"]["name"],
                        "home_team_tricode": game["home_team"]["abbreviation"],
                        "away_team": game["away_team"]["full_name"]
                        or game["away_team"]["name"],
                        "away_team_tricode": game["away_team"]["abbreviation"],
                        "venue": game["arena"],
                        "is_manual": False,
                        "home_team_option": home_option,
                        "away_team_option": away_option,
                    },
                )
                selected_ids.append(scheduled.nba_game_id)

                # Create PredictionEvent
                opens_at = min(now, game["game_time"])
                event, event_created = PredictionEvent.objects.update_or_create(
                    scheduled_game=scheduled,
                    defaults={
                        "tip_type": tip_type,
                        "name": f"{game['away_team']['abbreviation']} @ {game['home_team']['abbreviation']}",
                        "description": f"{game['away_team']['full_name']} at {game['home_team']['full_name']}",
                        "target_kind": PredictionEvent.TargetKind.TEAM,
                        "selection_mode": PredictionEvent.SelectionMode.CURATED,
                        "source_id": self.source_id,
                        "source_event_id": game["game_id"],
                        "metadata": {
                            "arena": game["arena"],
                            "home_team_data": game["home_team"],
                            "away_team_data": game["away_team"],
                        },
                        "opens_at": opens_at,
                        "deadline": game["game_time"],
                        "reveal_at": opens_at,
                        "is_active": True,
                        "sort_order": sort_index,
                        "points": tip_type.default_points,
                    },
                )

                if event_created:
                    result.events_created += 1
                else:
                    result.events_updated += 1

                event_ids.append(event.id)

                # Create prediction options
                if away_option:
                    PredictionOption.objects.update_or_create(
                        event=event,
                        option=away_option,
                        defaults={
                            "label": away_option.name,
                            "sort_order": 1,
                            "is_active": True,
                        },
                    )

                if home_option:
                    PredictionOption.objects.update_or_create(
                        event=event,
                        option=home_option,
                        defaults={
                            "label": home_option.name,
                            "sort_order": 2,
                            "is_active": True,
                        },
                    )

                # Remove options that aren't home or away
                valid_options = [opt for opt in [home_option, away_option] if opt]
                if valid_options:
                    PredictionOption.objects.filter(event=event).exclude(
                        option__in=valid_options
                    ).delete()

            # Clean up old games
            deleted_count, _ = (
                ScheduledGame.objects.filter(tip_type=tip_type, is_manual=False)
                .exclude(nba_game_id__in=selected_ids)
                .delete()
            )
            result.events_removed += deleted_count

            # Clean up events without scheduled games
            deleted_events, _ = (
                PredictionEvent.objects.filter(
                    tip_type=tip_type, scheduled_game__isnull=False
                )
                .exclude(id__in=event_ids)
                .delete()
            )
            result.events_removed += deleted_events

            logger.info(
                f"NBA sync completed: {result.events_created} created, "
                f"{result.events_updated} updated, {result.events_removed} removed"
            )

        except Exception as e:
            logger.exception(f"Error syncing NBA events: {e}")
            result.add_error(f"Failed to sync events: {str(e)}")

        return result

    def cleanup_old_events(self, keep_days: int = 30) -> EventSourceResult:
        """Clean up old NBA events."""
        result = EventSourceResult()

        cutoff_date = timezone.now() - timedelta(days=keep_days)

        try:
            # Delete old events
            deleted, _ = PredictionEvent.objects.filter(
                source_id=self.source_id, deadline__lt=cutoff_date
            ).delete()
            result.events_removed = deleted

        except Exception as e:
            logger.exception(f"Error cleaning up old NBA events: {e}")
            result.add_error(f"Failed to cleanup: {str(e)}")

        return result
