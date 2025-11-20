"""DBB app configuration."""

from django.apps import AppConfig


class DbbConfig(AppConfig):
    """Configuration for the DBB app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hooptipp.dbb'
    verbose_name = 'German Basketball (DBB)'

    def ready(self):
        """Register event source and card renderer when app is ready."""
        from hooptipp.predictions.event_sources.registry import register as register_event_source
        from hooptipp.predictions.card_renderers.registry import register as register_card_renderer
        
        from .event_source import DbbEventSource
        from .card_renderer import DbbCardRenderer
        
        # Register event source
        register_event_source(DbbEventSource)
        
        # Register card renderer
        register_card_renderer(DbbCardRenderer())

