from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path
from types import ModuleType

from django.test import SimpleTestCase


class DotenvSettingsTests(SimpleTestCase):
    """Validate dotenv integration for loading environment variables from .env file."""

    settings_module = 'hooptipp.settings'

    def setUp(self) -> None:  # noqa: D401 - Base class docstring sufficient.
        self._original_environ = os.environ.copy()
        self._temp_dir = None
        self._original_cwd = os.getcwd()

    def tearDown(self) -> None:  # noqa: D401 - Base class docstring sufficient.
        os.environ.clear()
        os.environ.update(self._original_environ)
        if self._temp_dir:
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        os.chdir(self._original_cwd)
        self._reload_settings()

    def _reload_settings(self) -> ModuleType:
        module = importlib.import_module(self.settings_module)
        return importlib.reload(module)

    def _create_temp_env_file(self, content: str) -> Path:
        """Create a temporary .env file and return its path."""
        self._temp_dir = tempfile.mkdtemp()
        env_file = Path(self._temp_dir) / '.env'
        env_file.write_text(content)
        return env_file

    def test_dotenv_loads_variables_from_env_file(self) -> None:
        """Test that variables from .env file are loaded into environment."""
        env_content = """
SECRET_KEY=test-secret-from-env
DEBUG=False
DATABASE_URL=postgresql://test:test@localhost:5432/testdb
DJANGO_ALLOWED_HOSTS=test.example.com,api.test.com
"""
        
        env_file = self._create_temp_env_file(env_content)
        
        # Clear environment variables that might interfere
        for key in ['SECRET_KEY', 'DEBUG', 'DATABASE_URL', 'DJANGO_ALLOWED_HOSTS']:
            os.environ.pop(key, None)
        
        # Test dotenv loading directly
        from dotenv import load_dotenv
        load_dotenv(env_file)
        
        # Verify that environment variables were loaded
        self.assertEqual(os.environ.get('SECRET_KEY'), 'test-secret-from-env')
        self.assertEqual(os.environ.get('DEBUG'), 'False')
        self.assertEqual(os.environ.get('DATABASE_URL'), 'postgresql://test:test@localhost:5432/testdb')
        self.assertEqual(os.environ.get('DJANGO_ALLOWED_HOSTS'), 'test.example.com,api.test.com')

    def test_dotenv_does_not_override_existing_env_variables(self) -> None:
        """Test that existing environment variables take precedence over .env file."""
        env_content = """
SECRET_KEY=env-file-secret
DEBUG=True
"""
        
        env_file = self._create_temp_env_file(env_content)
        
        # Set environment variables before loading .env
        os.environ['SECRET_KEY'] = 'existing-env-secret'
        os.environ['DEBUG'] = 'False'
        
        # Test dotenv loading directly
        from dotenv import load_dotenv
        load_dotenv(env_file)
        
        # Verify that existing environment variables were not overridden
        self.assertEqual(os.environ.get('SECRET_KEY'), 'existing-env-secret')
        self.assertEqual(os.environ.get('DEBUG'), 'False')

    def test_dotenv_handles_missing_env_file_gracefully(self) -> None:
        """Test that missing .env file doesn't cause errors."""
        # Create temp directory without .env file
        self._temp_dir = tempfile.mkdtemp()
        missing_env_file = Path(self._temp_dir) / '.env'
        
        # This should not raise an exception
        from dotenv import load_dotenv
        result = load_dotenv(missing_env_file)
        
        # Should return False when file doesn't exist
        self.assertFalse(result)

    def test_dotenv_handles_empty_env_file(self) -> None:
        """Test that empty .env file doesn't cause errors."""
        env_file = self._create_temp_env_file("")
        
        # This should not raise an exception
        from dotenv import load_dotenv
        result = load_dotenv(env_file)
        
        # Should return False when file is empty (no variables to load)
        self.assertFalse(result)
