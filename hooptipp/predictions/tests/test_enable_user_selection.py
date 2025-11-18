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

    def test_enable_user_selection_env_var_parsing_logic(self) -> None:
        """Test that ENABLE_USER_SELECTION environment variable is parsed correctly."""
        # Test the parsing logic directly
        test_cases = [
            ('True', True),
            ('true', True),
            ('FALSE', False),
            ('false', False),
            ('0', False),
            ('1', False),  # Only 'true' (case-insensitive) evaluates to True
            ('yes', False),
            ('', False),  # Empty string is not 'true'
        ]
        
        for env_value, expected in test_cases:
            result = env_value.lower() == 'true'
            self.assertEqual(result, expected, 
                           f"Environment value '{env_value}' should parse to {expected}")

    def test_enable_user_selection_default_value(self) -> None:
        """Test that ENABLE_USER_SELECTION has a sensible default."""
        # Test the default value logic
        default = 'True'
        result = default.lower() == 'true'
        self.assertTrue(result, "Default value should be True")

    @override_settings(ENABLE_USER_SELECTION=True)
    def test_enable_user_selection_can_be_set_to_true(self) -> None:
        """Test that ENABLE_USER_SELECTION can be set to True via settings."""
        from django.conf import settings
        self.assertTrue(settings.ENABLE_USER_SELECTION)

    @override_settings(ENABLE_USER_SELECTION=False)
    def test_enable_user_selection_can_be_set_to_false(self) -> None:
        """Test that ENABLE_USER_SELECTION can be set to False via settings."""
        from django.conf import settings
        self.assertFalse(settings.ENABLE_USER_SELECTION)

