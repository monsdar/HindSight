"""
Abstract base class for event sources.

Event sources are responsible for:
1. Importing options (e.g., teams, players, countries)
2. Importing/generating prediction events
3. Optionally resolving outcomes automatically
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

# Import PredictionEvent for RescheduledEvent dataclass
from ..models import PredictionEvent


@dataclass
class RescheduledEvent:
    """Information about a rescheduled event."""
    
    event: PredictionEvent
    old_deadline: datetime
    new_deadline: datetime
    reschedule_delta: timedelta


@dataclass
class EventSourceResult:
    """Result of an event source sync operation."""

    events_created: int = 0
    events_updated: int = 0
    events_removed: int = 0
    options_created: int = 0
    options_updated: int = 0
    options_removed: int = 0
    errors: list[str] = field(default_factory=list)
    rescheduled_events: list[RescheduledEvent] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """Return True if the sync operation made any changes."""
        return any(
            [
                self.events_created,
                self.events_updated,
                self.events_removed,
                self.options_created,
                self.options_updated,
                self.options_removed,
            ]
        )

    @property
    def has_errors(self) -> bool:
        """Return True if any errors occurred during sync."""
        return bool(self.errors)

    def add_error(self, error: str) -> None:
        """Add an error message to the result."""
        self.errors.append(error)

    def merge(self, other: EventSourceResult) -> None:
        """Merge another result into this one."""
        self.events_created += other.events_created
        self.events_updated += other.events_updated
        self.events_removed += other.events_removed
        self.options_created += other.options_created
        self.options_updated += other.options_updated
        self.options_removed += other.options_removed
        self.errors.extend(other.errors)
        self.rescheduled_events.extend(other.rescheduled_events)


class EventSource(ABC):
    """
    Abstract base class for event sources.

    Event sources are plugins that can automatically import prediction events
    from external systems (APIs, databases, etc.).

    To create a new event source:
    1. Subclass EventSource
    2. Implement all abstract methods
    3. Register the source in event_sources/__init__.py

    Example:
        class MyEventSource(EventSource):
            @property
            def source_id(self) -> str:
                return "my-source"

            @property
            def source_name(self) -> str:
                return "My Event Source"

            @property
            def category_slugs(self) -> list[str]:
                return ["my-category"]

            def sync_options(self) -> EventSourceResult:
                # Import options...
                return EventSourceResult(options_created=10)

            def sync_events(self) -> EventSourceResult:
                # Import events...
                return EventSourceResult(events_created=5)
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """
        Unique identifier for this event source.

        This is used to track which source created which events.
        Use lowercase with hyphens (e.g., "nba-balldontlie", "olympics-2028").
        """
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        Human-readable name for this event source.

        Displayed in admin interfaces and logs.
        """
        pass

    @property
    @abstractmethod
    def category_slugs(self) -> list[str]:
        """
        List of OptionCategory slugs this source provides.

        Example: ["nba-teams", "nba-players"] or ["countries"]
        """
        pass

    @abstractmethod
    def sync_options(self) -> EventSourceResult:
        """
        Import or update options from this source.

        This method should:
        1. Fetch options from the external source
        2. Create/update Option records in the database
        3. Return a result summarizing what changed

        Returns:
            EventSourceResult with counts of options created/updated/removed.
        """
        pass

    @abstractmethod
    def sync_events(self) -> EventSourceResult:
        """
        Import or update prediction events from this source.

        This method should:
        1. Fetch events from the external source
        2. Create/update PredictionEvent records
        3. Create/update PredictionOption records for each event
        4. Set source_id and source_event_id on created events
        5. Return a result summarizing what changed

        Returns:
            EventSourceResult with counts of events created/updated/removed.
        """
        pass

    def resolve_outcomes(self) -> EventSourceResult:
        """
        Optionally resolve outcomes for events automatically.

        Override this method if the source can automatically determine
        which option won an event (e.g., by fetching final scores).

        Default implementation does nothing.

        Returns:
            EventSourceResult with counts of outcomes resolved.
        """
        return EventSourceResult()

    def is_configured(self) -> bool:
        """
        Check if this event source is properly configured.

        Override to check for required API keys, credentials, etc.
        Sources that are not configured will be excluded from automatic syncs.

        Default implementation returns True (source is always available).

        Returns:
            True if the source is configured and ready to use.
        """
        return True

    def get_configuration_help(self) -> str:
        """
        Get help text for configuring this event source.

        Override to provide instructions on setting up API keys, etc.

        Returns:
            Help text string, or empty string if no configuration needed.
        """
        return ""

    def cleanup_old_events(self, keep_days: int = 30) -> EventSourceResult:
        """
        Clean up old events from this source.

        Override to implement custom cleanup logic for expired events.
        Default implementation does nothing.

        Args:
            keep_days: Number of days of events to keep after deadline.

        Returns:
            EventSourceResult with counts of events removed.
        """
        return EventSourceResult()

    def validate_event(self, event: PredictionEvent) -> list[str]:
        """
        Validate an event from this source.

        Override to implement source-specific validation rules.
        Default implementation returns no errors.

        Args:
            event: The event to validate.

        Returns:
            List of error messages, or empty list if valid.
        """
        return []

    def __str__(self) -> str:
        return f"{self.source_name} ({self.source_id})"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.source_id}>"
