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
        Sync NBA games as prediction events.

        Args:
            limit: Number of days to look ahead for games (unused for manual process).

        Returns:
            EventSourceResult with counts of events synced.
        """
        result = EventSourceResult()

        try:
            # Check for manual games
            tip_type = TipType.objects.filter(slug="weekly-games").first()
            if not tip_type:
                logger.info("No weekly-games tip type found")
                return result
                
            manual_games = ScheduledGame.objects.filter(
                tip_type=tip_type, is_manual=True
            ).order_by('game_date')
            
            if not manual_games.exists():
                logger.info("No manual games found")
                return result
                
            logger.info(f"Found {manual_games.count()} manual games")

            # Create events for manual games that don't have events yet
            teams_cat = NbaTeamManager.get_category()
            created_count = 0
            
            for scheduled_game in manual_games:
                # Check if event already exists
                existing_event = PredictionEvent.objects.filter(
                    scheduled_game=scheduled_game
                ).first()
                
                if existing_event:
                    continue
                    
                # Find team options
                home_option = Option.objects.filter(
                    category=teams_cat,
                    short_name=scheduled_game.home_team_tricode,
                ).first()

                away_option = Option.objects.filter(
                    category=teams_cat,
                    short_name=scheduled_game.away_team_tricode,
                ).first()

                # Create PredictionEvent
                opens_at = min(timezone.now(), scheduled_game.game_date)
                event, event_created = PredictionEvent.objects.update_or_create(
                    scheduled_game=scheduled_game,
                    defaults={
                        "tip_type": tip_type,
                        "name": f"{scheduled_game.away_team_tricode} @ {scheduled_game.home_team_tricode}",
                        "description": f"{scheduled_game.away_team} at {scheduled_game.home_team}",
                        "target_kind": PredictionEvent.TargetKind.TEAM,
                        "selection_mode": PredictionEvent.SelectionMode.CURATED,
                        "source_id": self.source_id,
                        "source_event_id": scheduled_game.nba_game_id,
                        "metadata": {
                            "arena": scheduled_game.venue,
                        },
                        "opens_at": opens_at,
                        "deadline": scheduled_game.game_date,
                        "reveal_at": opens_at,
                        "is_active": True,
                        "sort_order": 1,
                        "points": tip_type.default_points,
                    },
                )

                if event_created:
                    result.events_created += 1
                    created_count += 1

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

            logger.info(f"NBA manual sync completed: {created_count} events created")

        except Exception as e:
            logger.exception(f"Error syncing NBA manual events: {e}")
            result.add_error(f"Failed to sync manual events: {str(e)}")

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
