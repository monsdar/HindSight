from __future__ import annotations

import importlib
import os
from types import ModuleType

from django.test import SimpleTestCase


class CsrfTrustedOriginsSettingsTests(SimpleTestCase):
    """Validate configurable CSRF_TRUSTED_ORIGINS behaviour."""

    settings_module = 'hooptipp.settings'

    def setUp(self) -> None:  # noqa: D401 - Base class docstring sufficient.
        self._original_environ = os.environ.copy()

    def tearDown(self) -> None:  # noqa: D401 - Base class docstring sufficient.
        os.environ.clear()
        os.environ.update(self._original_environ)
        self._reload_settings()

    def _reload_settings(self) -> ModuleType:
        module = importlib.import_module(self.settings_module)
        return importlib.reload(module)

    def test_csrf_trusted_origins_include_allowed_host_origin(self) -> None:
        os.environ['DJANGO_ALLOWED_HOSTS'] = 'hooptipp-production.up.railway.app'
        os.environ.pop('DJANGO_CSRF_TRUSTED_ORIGINS', None)

        settings = self._reload_settings()

        self.assertIn(
            'https://hooptipp-production.up.railway.app',
            settings.CSRF_TRUSTED_ORIGINS,
        )

    def test_csrf_trusted_origins_extend_from_environment(self) -> None:
        os.environ['DJANGO_ALLOWED_HOSTS'] = 'hooptipp-production.up.railway.app'
        os.environ['DJANGO_CSRF_TRUSTED_ORIGINS'] = (
            'https://example.com, https://api.example.com '
        )

        settings = self._reload_settings()

        self.assertEqual(
            settings.CSRF_TRUSTED_ORIGINS,
            [
                'https://hooptipp-production.up.railway.app',
                'https://example.com',
                'https://api.example.com',
            ],
        )

