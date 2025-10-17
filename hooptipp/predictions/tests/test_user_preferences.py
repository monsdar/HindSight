from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from hooptipp.predictions.forms import UserPreferencesForm
from hooptipp.predictions.models import UserPreferences
from hooptipp.predictions.theme_palettes import DEFAULT_THEME_KEY, get_theme_palette


class UserPreferencesModelTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='preferences-user',
            password='password123',
        )

    def test_theme_palette_provides_defaults(self) -> None:
        preferences = UserPreferences.objects.create(user=self.user)
        palette = preferences.theme_palette()
        self.assertEqual(palette['primary'], '#f59e0b')
        self.assertEqual(palette['secondary'], '#0f172a')
        self.assertEqual(str(preferences), f'Preferences for {self.user}')
        self.assertEqual(preferences.theme, DEFAULT_THEME_KEY)

    def test_preferences_basic_fields(self) -> None:
        """Test that UserPreferences stores core fields (no NBA-specific fields)."""
        preferences = UserPreferences.objects.create(
            user=self.user,
            nickname='TestNick',
            theme='golden-state-warriors',
        )

        self.assertEqual(preferences.nickname, 'TestNick')
        self.assertEqual(preferences.theme, 'golden-state-warriors')
        self.assertIsNotNone(preferences.created_at)
        self.assertIsNotNone(preferences.updated_at)


class UserPreferencesFormTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='form-user',
            password='password123',
        )
        self.preferences = UserPreferences.objects.create(user=self.user)

    def test_form_persists_preferences(self) -> None:
        """Test that form saves core preference fields."""
        data = {
            'nickname': 'Ace',
            'theme': 'boston-celtics',
        }

        form = UserPreferencesForm(data=data, instance=self.preferences)
        self.assertTrue(form.is_valid())
        preferences = form.save()

        self.assertEqual(preferences.nickname, 'Ace')
        self.assertEqual(preferences.theme, 'boston-celtics')
        self.assertEqual(preferences.theme_palette(), get_theme_palette('boston-celtics'))

    def test_form_rejects_invalid_theme(self) -> None:
        """Test that form validates theme choices."""
        data = {
            'nickname': 'Ace',
            'theme': 'invalid-theme',
        }

        form = UserPreferencesForm(data=data, instance=self.preferences)
        self.assertFalse(form.is_valid())
        self.assertIn('theme', form.errors)
