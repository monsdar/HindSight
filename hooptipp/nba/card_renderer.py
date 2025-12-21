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
        # For backward compatibility, return long template if available, otherwise short
        long_template = self.get_event_template_long(event)
        if long_template:
            return long_template
        return self.get_event_template_short(event) or "nba/cards/game.html"

    def get_event_template_short(self, event: PredictionEvent) -> str | None:
        """Return short template for NBA events."""
        event_type = event.metadata.get("event_type", "game")
        
        # Only game events have short templates for now
        if event_type == "game":
            return "nba/cards/game_short.html"
        return None

    def get_event_template_long(self, event: PredictionEvent) -> str | None:
        """Return long template for NBA events."""
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
            
            # Add option IDs for team selection
            for option in event.options.all():
                if option.option.short_name == game.away_team_tricode:
                    context["away_team_option_id"] = option.id
                elif option.option.short_name == game.home_team_tricode:
                    context["home_team_option_id"] = option.id


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

        # Add result-specific data from EventOutcome metadata
        if outcome.metadata:
            game_result = outcome.metadata
            context.update({
                "away_score": game_result.get("away_score"),
                "home_score": game_result.get("home_score"),
                "game_status": game_result.get("game_status", "Final"),
            })

        # Add user score information if user is provided
        if user:
            from hooptipp.predictions.models import UserEventScore, UserTip
            try:
                user_score = UserEventScore.objects.get(
                    user=user,
                    prediction_event=outcome.prediction_event
                )
                context['user_score'] = user_score
            except UserEventScore.DoesNotExist:
                context['user_score'] = None
            
            # Calculate is_correct for the user's prediction
            try:
                user_tip = UserTip.objects.get(
                    user=user,
                    prediction_event=outcome.prediction_event
                )
                # Check if the user's prediction was correct
                if outcome.winning_option and user_tip.prediction_option:
                    context['is_correct'] = (user_tip.prediction_option.id == outcome.winning_option.id)
                elif outcome.winning_generic_option and user_tip.selected_option:
                    context['is_correct'] = (user_tip.selected_option.id == outcome.winning_generic_option.id)
                else:
                    context['is_correct'] = False
            except UserTip.DoesNotExist:
                context['is_correct'] = False
        else:
            context['user_score'] = None
            context['is_correct'] = False

        return context

    @property
    def priority(self) -> int:
        """NBA renderer has normal priority."""
        return 0
