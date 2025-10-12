from __future__ import annotations

import importlib
import os
from types import ModuleType

from django.test import SimpleTestCase


class DatabaseSettingsTests(SimpleTestCase):
    """Validate dynamic database configuration selection."""

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

    def test_sqlite_used_when_no_database_env_is_present(self) -> None:
        os.environ.pop('DATABASE_URL', None)
        os.environ.pop('POSTGRES_DB', None)
        os.environ.pop('POSTGRES_USER', None)
        os.environ.pop('POSTGRES_PASSWORD', None)
        os.environ.pop('POSTGRES_HOST', None)
        os.environ.pop('POSTGRES_PORT', None)

        settings = self._reload_settings()
        default_config = settings.DATABASES['default']

        self.assertEqual(default_config['ENGINE'], 'django.db.backends.sqlite3')
        self.assertTrue(str(default_config['NAME']).endswith('db.sqlite3'))

    def test_database_url_configuration_selects_postgres(self) -> None:
        os.environ['DATABASE_URL'] = 'postgresql://user:secret@db.example.com:5433/sample_db?sslmode=require'
        os.environ['DATABASE_CONN_MAX_AGE'] = '600'

        settings = self._reload_settings()
        default_config = settings.DATABASES['default']

        self.assertEqual(default_config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(default_config['NAME'], 'sample_db')
        self.assertEqual(default_config['USER'], 'user')
        self.assertEqual(default_config['PASSWORD'], 'secret')
        self.assertEqual(default_config['HOST'], 'db.example.com')
        self.assertEqual(default_config['PORT'], '5433')
        self.assertEqual(default_config['CONN_MAX_AGE'], 600)
        self.assertEqual(default_config['OPTIONS']['sslmode'], 'require')

    def test_postgres_env_configuration_without_url(self) -> None:
        os.environ.pop('DATABASE_URL', None)
        os.environ['POSTGRES_DB'] = 'hooptipp'
        os.environ['POSTGRES_USER'] = 'app-user'
        os.environ['POSTGRES_PASSWORD'] = 'password123'
        os.environ['POSTGRES_HOST'] = 'postgres.internal'
        os.environ['POSTGRES_PORT'] = '5432'
        os.environ['POSTGRES_SSL_MODE'] = 'require'
        os.environ['POSTGRES_CONN_MAX_AGE'] = '120'

        settings = self._reload_settings()
        default_config = settings.DATABASES['default']

        self.assertEqual(default_config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(default_config['NAME'], 'hooptipp')
        self.assertEqual(default_config['USER'], 'app-user')
        self.assertEqual(default_config['PASSWORD'], 'password123')
        self.assertEqual(default_config['HOST'], 'postgres.internal')
        self.assertEqual(default_config['PORT'], '5432')
        self.assertEqual(default_config['CONN_MAX_AGE'], 120)
        self.assertEqual(default_config['OPTIONS']['sslmode'], 'require')
