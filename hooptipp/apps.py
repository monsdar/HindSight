from django.apps import AppConfig


class HooptippConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hooptipp'

    def ready(self) -> None:  # pragma: no cover - signal wiring
        from django.db.models.signals import post_migrate

        from .admin_setup import ensure_default_superuser

        post_migrate.connect(
            ensure_default_superuser,
            dispatch_uid='hooptipp.ensure_default_superuser',
        )
