"""Demo card renderer for prediction events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hooptipp.predictions.card_renderers.base import CardRenderer

if TYPE_CHECKING:
    from hooptipp.predictions.models import EventOutcome, PredictionEvent


class DemoCardRenderer(CardRenderer):
    """Card renderer for demo prediction events."""

    def can_render(self, event: PredictionEvent) -> bool:
        """Check if this is a demo event."""
        return event.source_id == "demo"

    def get_event_template(self, event: PredictionEvent) -> str:
        """Return appropriate demo template based on event type."""
        event_type = event.metadata.get("event_type", "generic")

        template_map = {
            "yesno": "demo/cards/yesno.html",
            "colors": "demo/cards/colors.html",
            "bonus": "demo/cards/bonus.html",
            "player": "demo/cards/player.html",
        }

        return template_map.get(event_type, "demo/cards/generic.html")

    def get_result_template(self, outcome: EventOutcome) -> str:
        """Return appropriate demo template for resolved predictions."""
        event = outcome.prediction_event
        event_type = event.metadata.get("event_type", "generic")

        template_map = {
            "yesno": "demo/cards/yesno_result.html",
            "colors": "demo/cards/colors_result.html",
            "bonus": "demo/cards/bonus_result.html",
            "player": "demo/cards/player_result.html",
        }

        return template_map.get(event_type, "demo/cards/generic_result.html")

    def get_event_context(self, event: PredictionEvent, user=None) -> dict:
        """Provide demo-specific card data."""
        context = {
            'demo': True,
            'event_type': event.metadata.get('event_type', 'generic'),
        }
        
        # Add color data for color events
        if event.metadata.get('event_type') == 'colors':
            colors_data = {}
            for option in event.options.all():
                if option.option and option.option.metadata.get('color'):
                    colors_data[option.option.id] = option.option.metadata['color']
            context['colors'] = colors_data
        
        # Add special flag for bonus events
        if event.metadata.get('special'):
            context['special'] = True
        
        return context

    def get_result_context(self, outcome: EventOutcome, user=None) -> dict:
        """Provide demo-specific result card data."""
        # Start with event context
        context = self.get_event_context(outcome.prediction_event, user)
        
        # Add result-specific data
        context['outcome'] = outcome
        
        return context

    @property
    def priority(self) -> int:
        """Demo renderer has normal priority."""
        return 0
