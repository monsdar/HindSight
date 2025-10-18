"""Demo app configuration."""

from django.apps import AppConfig


class DemoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hooptipp.demo'
    verbose_name = 'Demo'
    
    def ready(self):
        """Register demo card renderer on app ready."""
        from hooptipp.predictions.card_renderers.registry import register
        from .card_renderer import DemoCardRenderer
        
        register(DemoCardRenderer())
