"""NBA card renderer for prediction events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hooptipp.predictions.card_renderers.base import CardRenderer

if TYPE_CHECKING:
    from hooptipp.predictions.models import EventOutcome, PredictionEvent


class NbaCardRenderer(CardRenderer):
    """Card renderer for NBA prediction events."""

    def can_render(self, event: PredictionEvent) -> bool:
        """Check if this is an NBA event."""
        return event.source_id == "nba-balldontlie"

    def get_event_template(self, event: PredictionEvent) -> str:
        """Return appropriate NBA template based on event type."""
        event_type = event.metadata.get("event_type", "game")

        template_map = {
            "game": "nba/cards/game.html",
            "mvp": "nba/cards/mvp.html",
            "playoff_series": "nba/cards/playoff_series.html",
        }

        return template_map.get(event_type, "nba/cards/game.html")

    def get_result_template(self, outcome: EventOutcome) -> str:
        """Return appropriate NBA template for resolved predictions."""
        event = outcome.prediction_event
        event_type = event.metadata.get("event_type", "game")

        # Could have separate result templates if desired
        # For now, reuse event templates with outcome context
        template_map = {
            "game": "nba/cards/game_result.html",
            "mvp": "nba/cards/mvp.html",
            "playoff_series": "nba/cards/playoff_series.html",
        }

        return template_map.get(event_type, "nba/cards/game_result.html")

    def get_event_context(self, event: PredictionEvent, user=None) -> dict:
        """Provide NBA-specific card data."""
        from .services import (
            get_mvp_standings,
            get_player_card_data,
            get_team_logo_url,
        )

        context = {}
        event_type = event.metadata.get("event_type", "game")

        if event_type == "game" and event.scheduled_game:
            # Game card data
            game = event.scheduled_game
            context.update(
                {
                    "away_team": game.away_team,
                    "away_team_tricode": game.away_team_tricode,
                    "away_team_logo": get_team_logo_url(game.away_team_tricode),
                    "home_team": game.home_team,
                    "home_team_tricode": game.home_team_tricode,
                    "home_team_logo": get_team_logo_url(game.home_team_tricode),
                    "venue": game.venue,
                    "game_time": game.game_date,
                }
            )


            # Add playoff context if applicable
            if "playoff_series" in event.metadata:
                series = event.metadata["playoff_series"]
                context["playoff_context"] = {
                    "series_name": series["name"],
                    "game_number": series["game_number"],
                    "series_score": series.get("series_score"),
                }

        elif event_type == "mvp":
            # MVP card data
            context["players"] = {}
            for option in event.options.all():
                player_data = get_player_card_data(option.option.external_id)
                context["players"][option.option.id] = player_data

            context["mvp_standings"] = get_mvp_standings()

        return context

    def get_result_context(self, outcome: EventOutcome, user=None) -> dict:
        """Provide NBA-specific result card data."""
        # Start with event context
        context = self.get_event_context(outcome.prediction_event, user)

        # Add result-specific data
        if outcome.prediction_event.scheduled_game:
            game = outcome.prediction_event.scheduled_game
            # Note: Final scores are not stored in the ScheduledGame model
            # They would need to be fetched from external API if needed

        # Add user score information if user is provided
        if user:
            from hooptipp.predictions.models import UserEventScore
            try:
                user_score = UserEventScore.objects.get(
                    user=user,
                    prediction_event=outcome.prediction_event
                )
                context['user_score'] = user_score
            except UserEventScore.DoesNotExist:
                context['user_score'] = None
        else:
            context['user_score'] = None

        return context

    @property
    def priority(self) -> int:
        """NBA renderer has normal priority."""
        return 0
