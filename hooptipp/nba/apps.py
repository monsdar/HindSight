"""NBA app configuration."""

from django.apps import AppConfig


class NbaConfig(AppConfig):
    """Configuration for the NBA predictions app."""

    name = 'hooptipp.nba'
    verbose_name = 'NBA Predictions'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        """Initialize NBA app - register event source and preferences."""
        # Register NBA event source
        from hooptipp.predictions.event_sources import registry
        from .event_source import NbaEventSource
        registry.register(NbaEventSource)

        # Register NBA preferences
        from hooptipp.predictions.preferences_registry import (
            preferences_registry,
            PreferenceSection,
        )
        from .models import NbaUserPreferences

        preferences_registry.register(
            PreferenceSection(
                app_name='nba',
                model=NbaUserPreferences,
                favorite_types=['nba-team', 'nba-player'],
            )
        )
