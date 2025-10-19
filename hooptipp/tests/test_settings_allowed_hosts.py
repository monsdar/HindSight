from __future__ import annotations

import importlib
import os
from types import ModuleType
from unittest import mock

from django.test import SimpleTestCase


class AllowedHostsSettingsTests(SimpleTestCase):
    """Validate configurable ALLOWED_HOSTS behaviour."""

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

    def test_allowed_hosts_defaults_to_empty_list(self) -> None:
        # Clear the environment variable and ensure no .env file is loaded
        os.environ.pop('DJANGO_ALLOWED_HOSTS', None)
        
        # Mock the load_dotenv function to prevent loading .env file
        # We need to patch it at the module level before importing
        with mock.patch('dotenv.load_dotenv'):
            settings = self._reload_settings()

        self.assertEqual(settings.ALLOWED_HOSTS, [])

    def test_allowed_hosts_appends_entries_from_environment(self) -> None:
        os.environ['DJANGO_ALLOWED_HOSTS'] = 'example.com, api.example.com , '

        settings = self._reload_settings()

        self.assertEqual(settings.ALLOWED_HOSTS, ['example.com', 'api.example.com'])
