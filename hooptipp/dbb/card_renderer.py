"""DBB card renderer for prediction events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hooptipp.predictions.card_renderers.base import CardRenderer

from .logo_matcher import find_logo_for_team

if TYPE_CHECKING:
    from hooptipp.predictions.models import EventOutcome, PredictionEvent


class DbbCardRenderer(CardRenderer):
    """Card renderer for DBB prediction events."""

    def can_render(self, event: PredictionEvent) -> bool:
        """Check if this is a DBB event."""
        return event.source_id == "dbb-slapi"

    def get_event_template(self, event: PredictionEvent) -> str:
        """Return DBB match template."""
        return "dbb/cards/match.html"

    def get_result_template(self, outcome: EventOutcome) -> str:
        """Return DBB match result template."""
        return "dbb/cards/match_result.html"

    def get_event_context(self, event: PredictionEvent, user=None) -> dict:
        """Provide DBB-specific card data."""
        context = {}

        # Extract match information from metadata
        metadata = event.metadata or {}
        
        context.update({
            'league_name': metadata.get('league_name', ''),
            'verband_name': metadata.get('verband_name', ''),
            'venue': metadata.get('venue', ''),
            'match_time': event.deadline,
        })

        # Add team information from options
        for option in event.options.all():
            if option.sort_order == 1:  # Away team
                context['away_team'] = option.label
                context['away_team_option_id'] = option.id
                # Extract logo from option metadata, or discover dynamically
                logo = ''
                if option.option and option.option.metadata:
                    logo = option.option.metadata.get('logo', '')
                # If no logo in metadata, try dynamic discovery
                if not logo:
                    logo = find_logo_for_team(option.label)
                context['away_team_logo'] = logo
            elif option.sort_order == 2:  # Home team
                context['home_team'] = option.label
                context['home_team_option_id'] = option.id
                # Extract logo from option metadata, or discover dynamically
                logo = ''
                if option.option and option.option.metadata:
                    logo = option.option.metadata.get('logo', '')
                # If no logo in metadata, try dynamic discovery
                if not logo:
                    logo = find_logo_for_team(option.label)
                context['home_team_logo'] = logo

        return context

    def get_result_context(self, outcome: EventOutcome, user=None) -> dict:
        """Provide DBB-specific result card data."""
        # Start with event context
        context = self.get_event_context(outcome.prediction_event, user)

        # Add result-specific data from EventOutcome metadata
        if outcome.metadata:
            match_result = outcome.metadata
            context.update({
                'home_score': match_result.get('home_score'),
                'away_score': match_result.get('away_score'),
                'match_status': match_result.get('match_status', 'Final'),
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
        """DBB renderer has normal priority."""
        return 0

