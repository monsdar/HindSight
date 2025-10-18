"""
Registry for card renderers.

Extensions register their custom card renderers here.
The registry finds the appropriate renderer for each event.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import CardRenderer, DefaultCardRenderer

if TYPE_CHECKING:
    from ..models import PredictionEvent


class CardRendererRegistry:
    """
    Registry for card renderers.

    Extensions register their custom card renderers here.
    The registry finds the appropriate renderer for each event.
    """

    def __init__(self):
        self._renderers: list[CardRenderer] = []
        # Always have a default fallback
        self._default_renderer = DefaultCardRenderer()

    def register(self, renderer: CardRenderer) -> None:
        """
        Register a card renderer.

        Args:
            renderer: CardRenderer instance to register
        """
        self._renderers.append(renderer)
        # Sort by priority (highest first)
        self._renderers.sort(key=lambda r: r.priority, reverse=True)

    def get_renderer(self, event: PredictionEvent) -> CardRenderer:
        """
        Find the appropriate renderer for an event.

        Checks registered renderers in priority order.
        Falls back to default renderer if none match.

        Args:
            event: PredictionEvent instance

        Returns:
            CardRenderer instance that can render this event
        """
        for renderer in self._renderers:
            if renderer.can_render(event):
                return renderer

        return self._default_renderer

    def list_renderers(self) -> list[CardRenderer]:
        """Return all registered renderers."""
        return self._renderers.copy()


# Global registry instance
registry = CardRendererRegistry()


def register(renderer: CardRenderer) -> None:
    """
    Convenience function to register a card renderer.

    Usage:
        from hooptipp.predictions.card_renderers.registry import register
        register(MyCardRenderer())
    """
    registry.register(renderer)
