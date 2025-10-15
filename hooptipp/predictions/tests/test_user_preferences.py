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

    def test_display_helpers_resolve_labels(self) -> None:
        preferences = UserPreferences.objects.create(
            user=self.user,
            favorite_team_id=14,
            favorite_player_id=23,
        )

        with mock.patch('hooptipp.predictions.services.get_team_choices', return_value=[('14', 'Los Angeles Lakers')]), \
                mock.patch('hooptipp.predictions.services.get_player_choices', return_value=[('23', 'LeBron James')]):
            self.assertEqual(preferences.favorite_team_display(), 'Los Angeles Lakers')
            self.assertEqual(preferences.favorite_player_display(), 'LeBron James')


class UserPreferencesFormTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='form-user',
            password='password123',
        )
        self.preferences = UserPreferences.objects.create(user=self.user)

    def test_form_persists_preferences(self) -> None:
        data = {
            'nickname': 'Ace',
            'favorite_team_id': '5',
            'favorite_player_id': '7',
            'theme': 'boston-celtics',
        }

        with mock.patch('hooptipp.predictions.forms.get_team_choices', return_value=[('5', 'Boston Celtics')]), \
                mock.patch('hooptipp.predictions.forms.get_player_choices', return_value=[('7', 'Jaylen Brown')]):
            form = UserPreferencesForm(data=data, instance=self.preferences)
            self.assertTrue(form.is_valid())
            preferences = form.save()

        self.assertEqual(preferences.nickname, 'Ace')
        self.assertEqual(preferences.favorite_team_id, 5)
        self.assertEqual(preferences.favorite_player_id, 7)
        self.assertEqual(preferences.theme, 'boston-celtics')
        self.assertEqual(preferences.theme_palette(), get_theme_palette('boston-celtics'))

    def test_form_rejects_invalid_theme(self) -> None:
        data = {
            'nickname': 'Ace',
            'favorite_team_id': '',
            'favorite_player_id': '',
            'theme': 'invalid-theme',
        }

        with mock.patch('hooptipp.predictions.forms.get_team_choices', return_value=[]), \
                mock.patch('hooptipp.predictions.forms.get_player_choices', return_value=[]):
            form = UserPreferencesForm(data=data, instance=self.preferences)
            self.assertFalse(form.is_valid())
            self.assertIn('theme', form.errors)
