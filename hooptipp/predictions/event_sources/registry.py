"""
Registry for event sources.

The registry maintains a list of all available event sources and provides
methods to access them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import EventSource

logger = logging.getLogger(__name__)


class EventSourceRegistry:
    """Registry for all available event sources."""

    def __init__(self) -> None:
        self._sources: dict[str, type[EventSource]] = {}

    def register(self, source_class: type[EventSource]) -> None:
        """
        Register an event source class.

        Args:
            source_class: The EventSource subclass to register.

        Raises:
            ValueError: If a source with the same ID is already registered.
        """
        # Instantiate to get the source_id
        try:
            instance = source_class()
        except Exception as e:
            logger.error(
                f"Failed to instantiate event source {source_class.__name__}: {e}"
            )
            return

        source_id = instance.source_id

        if source_id in self._sources:
            logger.warning(
                f"Event source {source_id} is already registered, skipping duplicate"
            )
            return

        self._sources[source_id] = source_class
        logger.info(
            f"Registered event source: {instance.source_name} ({source_id})"
        )

    def unregister(self, source_id: str) -> None:
        """
        Unregister an event source.

        Args:
            source_id: The ID of the source to unregister.
        """
        if source_id in self._sources:
            del self._sources[source_id]
            logger.info(f"Unregistered event source: {source_id}")

    def get(self, source_id: str) -> EventSource:
        """
        Get an event source instance by ID.

        Args:
            source_id: The unique identifier of the source.

        Returns:
            An instance of the requested EventSource.

        Raises:
            ValueError: If the source ID is not registered.
        """
        source_class = self._sources.get(source_id)
        if not source_class:
            available = ", ".join(self._sources.keys())
            raise ValueError(
                f"Unknown event source: {source_id}. "
                f"Available sources: {available or 'none'}"
            )
        return source_class()

    def list_sources(self) -> list[EventSource]:
        """
        List all registered event sources.

        Returns:
            List of EventSource instances for all registered sources.
        """
        sources = []
        for source_class in self._sources.values():
            try:
                sources.append(source_class())
            except Exception as e:
                logger.error(
                    f"Failed to instantiate {source_class.__name__}: {e}"
                )
        return sources

    def list_configured_sources(self) -> list[EventSource]:
        """
        List only properly configured event sources.

        Returns:
            List of EventSource instances that are configured and ready to use.
        """
        return [source for source in self.list_sources() if source.is_configured()]

    def get_sources_for_category(self, category_slug: str) -> list[EventSource]:
        """
        Get all sources that provide a specific option category.

        Args:
            category_slug: The slug of the category to search for.

        Returns:
            List of EventSource instances that provide the category.
        """
        return [
            source
            for source in self.list_sources()
            if category_slug in source.category_slugs
        ]

    def is_registered(self, source_id: str) -> bool:
        """
        Check if a source is registered.

        Args:
            source_id: The ID to check.

        Returns:
            True if the source is registered.
        """
        return source_id in self._sources

    def clear(self) -> None:
        """Clear all registered sources (useful for testing)."""
        self._sources.clear()


# Global registry instance
registry = EventSourceRegistry()


# Convenience functions that use the global registry
def get_source(source_id: str) -> EventSource:
    """Get an event source by ID."""
    return registry.get(source_id)


def list_sources() -> list[EventSource]:
    """List all registered event sources."""
    return registry.list_sources()


def list_configured_sources() -> list[EventSource]:
    """List only configured event sources."""
    return registry.list_configured_sources()


def register(source_class: type[EventSource]) -> None:
    """Register an event source."""
    registry.register(source_class)
