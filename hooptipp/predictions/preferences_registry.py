"""
Preference registry for managing app-specific user preferences.

This allows each sport/domain app to register its own preference models
while maintaining a unified interface for accessing them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Type
    from django.db import models
    from django.contrib.auth.models import User


class PreferenceSection:
    """Represents a section of preferences from an app."""

    def __init__(
        self,
        app_name: str,
        model: Type[models.Model],
        favorite_types: list[str] | None = None,
    ):
        """
        Initialize a preference section.

        Args:
            app_name: Name of the app (e.g., 'nba', 'olympics')
            model: The preference model class
            favorite_types: List of favorite types this app uses (e.g., ['nba-team', 'nba-player'])
        """
        self.app_name = app_name
        self.model = model
        self.favorite_types = favorite_types or []

    def get_or_create(self, user: User) -> tuple[Any, bool]:
        """Get or create preferences for user."""
        return self.model.objects.get_or_create(user=user)


class PreferencesRegistry:
    """Registry for app-specific preference models."""

    def __init__(self):
        self._sections: dict[str, PreferenceSection] = {}

    def register(self, section: PreferenceSection) -> None:
        """Register a preference section."""
        self._sections[section.app_name] = section

    def get_section(self, app_name: str) -> PreferenceSection | None:
        """Get preference section for an app."""
        return self._sections.get(app_name)

    def get_all_sections(self) -> list[PreferenceSection]:
        """Get all registered preference sections."""
        return list(self._sections.values())

    def get_user_preferences(self, user: User) -> dict[str, Any]:
        """Get all preferences for a user across all apps."""
        prefs = {}
        for app_name, section in self._sections.items():
            prefs[app_name], _ = section.get_or_create(user)
        return prefs


# Global registry instance
preferences_registry = PreferencesRegistry()
