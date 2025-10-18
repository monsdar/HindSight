"""
Base classes for card renderers.

Card renderers determine which templates to use and what context data to provide
for rendering prediction event cards and result cards in the UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import EventOutcome, PredictionEvent


class CardRenderer(ABC):
    """
    Abstract base class for rendering prediction event cards.

    Card renderers are responsible for:
    1. Determining which template to use for an event
    2. Providing context data for the template
    3. Optionally determining which template to use for resolved events
    """

    @abstractmethod
    def can_render(self, event: PredictionEvent) -> bool:
        """
        Check if this renderer can handle the given event.

        Typically checks event.source_id or event metadata.

        Args:
            event: PredictionEvent instance

        Returns:
            True if this renderer can render the event
        """
        pass

    @abstractmethod
    def get_event_template(self, event: PredictionEvent) -> str:
        """
        Return the template path for rendering an open prediction event.

        Args:
            event: PredictionEvent instance

        Returns:
            Template path relative to templates directory
            Example: 'nba/cards/game.html'
        """
        pass

    def get_result_template(self, outcome: EventOutcome) -> str:
        """
        Return the template path for rendering a resolved prediction result.

        Override to provide custom result card templates.
        Defaults to using the same template as the event card.

        Args:
            outcome: EventOutcome instance

        Returns:
            Template path relative to templates directory
        """
        return self.get_event_template(outcome.prediction_event)
    
    def get_result_context(self, outcome: EventOutcome, user=None) -> dict:
        """
        Return additional context data for rendering the result card.

        Override to provide result-specific data.
        Defaults to using the same context as the event card.

        Args:
            outcome: EventOutcome instance
            user: Optional active user for personalization

        Returns:
            Dictionary of context variables for the template
        """
        return self.get_event_context(outcome.prediction_event, user)

    def get_event_context(self, event: PredictionEvent, user=None) -> dict:
        """
        Return additional context data for rendering the event card.

        Override to provide event-specific data like:
        - Team logos, player portraits
        - Live scores, game status
        - Additional metadata

        Args:
            event: PredictionEvent instance
            user: Optional active user for personalization

        Returns:
            Dictionary of context variables for the template
        """
        return {}

    def get_result_context(self, outcome: EventOutcome, user=None) -> dict:
        """
        Return additional context data for rendering the result card.

        Override to provide result-specific data.
        Defaults to using the same context as the event card.

        Args:
            outcome: EventOutcome instance
            user: Optional active user for personalization

        Returns:
            Dictionary of context variables for the template
        """
        return self.get_event_context(outcome.prediction_event, user)

    @property
    def priority(self) -> int:
        """
        Return the priority of this renderer (higher = checked first).

        Useful when multiple renderers might match an event.
        Default priority is 0.
        """
        return 0


class DefaultCardRenderer(CardRenderer):
    """Default card renderer that handles any event without a specific renderer."""

    def can_render(self, event: PredictionEvent) -> bool:
        """Default renderer accepts any event."""
        return True

    def get_event_template(self, event: PredictionEvent) -> str:
        """Use the default generic card template."""
        return "predictions/cards/default.html"
    
    def get_result_template(self, outcome: EventOutcome) -> str:
        """Use the default generic result card template."""
        return "predictions/cards/default_result.html"

    @property
    def priority(self) -> int:
        """Lowest priority - only used as fallback."""
        return -1000
