"""Tests for ENABLE_USER_SELECTION environment variable."""
from __future__ import annotations

import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


class EnableUserSelectionSettingTests(TestCase):
    """Test the ENABLE_USER_SELECTION setting behavior."""

    def setUp(self) -> None:
        """Set up test user."""
        User = get_user_model()
        self.user = User.objects.create_user(username='testuser', password='testpass123')

    @override_settings(ENABLE_USER_SELECTION=True)
    def test_user_selection_enabled_by_default(self) -> None:
        """Test that user selection is enabled when ENABLE_USER_SELECTION is True."""
        response = self.client.get(reverse('predictions:home'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['enable_user_selection'])
        
        # Check that the user selection section is in the rendered HTML
        self.assertContains(response, 'Select Player')

    @override_settings(ENABLE_USER_SELECTION=False)
    def test_user_selection_disabled(self) -> None:
        """Test that user selection is disabled when ENABLE_USER_SELECTION is False."""
        response = self.client.get(reverse('predictions:home'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['enable_user_selection'])
        
        # Check that the user selection section is NOT in the rendered HTML
        self.assertNotContains(response, 'Select Player')

    @override_settings(ENABLE_USER_SELECTION=True)
    def test_user_selection_shows_finish_predictions_button_when_active(self) -> None:
        """Test that Finish Predictions button is shown when user is active and selection enabled."""
        # Activate a user in the session
        session = self.client.session
        session['active_user_id'] = self.user.id
        session.save()
        
        response = self.client.get(reverse('predictions:home'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['enable_user_selection'])
        
        # Check that the Finish Predictions button is in the rendered HTML
        self.assertContains(response, 'Finish Predictions')

    @override_settings(ENABLE_USER_SELECTION=False)
    def test_user_selection_hides_finish_predictions_button_when_disabled(self) -> None:
        """Test that Finish Predictions button is hidden when user selection is disabled."""
        # Activate a user in the session
        session = self.client.session
        session['active_user_id'] = self.user.id
        session.save()
        
        response = self.client.get(reverse('predictions:home'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['enable_user_selection'])
        
        # Check that the Finish Predictions button is NOT in the rendered HTML
        self.assertNotContains(response, 'Finish Predictions')

    @override_settings(ENABLE_USER_SELECTION=True)
    def test_user_selection_shows_pin_modal(self) -> None:
        """Test that PIN modal is shown when user selection is enabled."""
        response = self.client.get(reverse('predictions:home'))
        self.assertEqual(response.status_code, 200)
        
        # Check that the PIN modal is in the rendered HTML
        self.assertContains(response, 'pin-modal')
        self.assertContains(response, 'Enter Activation PIN')

    @override_settings(ENABLE_USER_SELECTION=False)
    def test_user_selection_hides_pin_modal(self) -> None:
        """Test that PIN modal is hidden when user selection is disabled."""
        response = self.client.get(reverse('predictions:home'))
        self.assertEqual(response.status_code, 200)
        
        # Check that the PIN modal is NOT in the rendered HTML
        self.assertNotContains(response, 'pin-modal')
        self.assertNotContains(response, 'Enter Activation PIN')


class EnableUserSelectionEnvVarTests(TestCase):
    """Test ENABLE_USER_SELECTION environment variable parsing."""

    def test_enable_user_selection_defaults_to_true_when_not_set(self) -> None:
        """Test that ENABLE_USER_SELECTION defaults to True when environment variable is not set."""
        with mock.patch.dict(os.environ, {}, clear=False):
            # Remove the ENABLE_USER_SELECTION env var if it exists
            os.environ.pop('ENABLE_USER_SELECTION', None)
            
            # Reload settings to pick up the change
            from django.conf import settings
            from importlib import reload
            import hooptipp.settings as settings_module
            reload(settings_module)
            
            # The default should be True
            self.assertTrue(settings_module.ENABLE_USER_SELECTION)

    def test_enable_user_selection_true_when_set_to_true(self) -> None:
        """Test that ENABLE_USER_SELECTION is True when environment variable is 'True'."""
        with mock.patch.dict(os.environ, {'ENABLE_USER_SELECTION': 'True'}, clear=False):
            # Reload settings to pick up the change
            from django.conf import settings
            from importlib import reload
            import hooptipp.settings as settings_module
            reload(settings_module)
            
            self.assertTrue(settings_module.ENABLE_USER_SELECTION)

    def test_enable_user_selection_true_when_set_to_true_lowercase(self) -> None:
        """Test that ENABLE_USER_SELECTION is True when environment variable is 'true'."""
        with mock.patch.dict(os.environ, {'ENABLE_USER_SELECTION': 'true'}, clear=False):
            # Reload settings to pick up the change
            from django.conf import settings
            from importlib import reload
            import hooptipp.settings as settings_module
            reload(settings_module)
            
            self.assertTrue(settings_module.ENABLE_USER_SELECTION)

    def test_enable_user_selection_false_when_set_to_false(self) -> None:
        """Test that ENABLE_USER_SELECTION is False when environment variable is 'False'."""
        with mock.patch.dict(os.environ, {'ENABLE_USER_SELECTION': 'False'}, clear=False):
            # Reload settings to pick up the change
            from django.conf import settings
            from importlib import reload
            import hooptipp.settings as settings_module
            reload(settings_module)
            
            self.assertFalse(settings_module.ENABLE_USER_SELECTION)

    def test_enable_user_selection_false_when_set_to_false_lowercase(self) -> None:
        """Test that ENABLE_USER_SELECTION is False when environment variable is 'false'."""
        with mock.patch.dict(os.environ, {'ENABLE_USER_SELECTION': 'false'}, clear=False):
            # Reload settings to pick up the change
            from django.conf import settings
            from importlib import reload
            import hooptipp.settings as settings_module
            reload(settings_module)
            
            self.assertFalse(settings_module.ENABLE_USER_SELECTION)

    def test_enable_user_selection_false_when_set_to_0(self) -> None:
        """Test that ENABLE_USER_SELECTION is False when environment variable is '0'."""
        with mock.patch.dict(os.environ, {'ENABLE_USER_SELECTION': '0'}, clear=False):
            # Reload settings to pick up the change
            from django.conf import settings
            from importlib import reload
            import hooptipp.settings as settings_module
            reload(settings_module)
            
            self.assertFalse(settings_module.ENABLE_USER_SELECTION)

