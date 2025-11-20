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
        # Get the expected palette from the default theme
        expected_palette = get_theme_palette(DEFAULT_THEME_KEY)
        self.assertEqual(palette['primary'], expected_palette['primary'])
        self.assertEqual(palette['secondary'], expected_palette['secondary'])
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

    def test_form_includes_activation_pin_field(self) -> None:
        """Test that form includes activation_pin field."""
        form = UserPreferencesForm(instance=self.preferences)
        self.assertIn('activation_pin', form.fields)
        self.assertEqual(form.fields['activation_pin'].label, 'Activation PIN')


class UserPreferencesPinTests(TestCase):
    """Tests for PIN functionality in UserPreferences."""
    
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='pin-user',
            password='password123',
        )
        self.preferences = UserPreferences.objects.create(user=self.user)

    def test_get_pin_teams_empty(self) -> None:
        """Test getting PIN teams when none are set."""
        self.assertEqual(self.preferences.get_pin_teams(), [])

    def test_get_pin_teams_with_data(self) -> None:
        """Test getting PIN teams when set."""
        self.preferences.activation_pin = 'LAL,GSW,BOS'
        self.preferences.save()
        
        teams = self.preferences.get_pin_teams()
        self.assertEqual(teams, ['LAL', 'GSW', 'BOS'])

    def test_get_pin_teams_with_whitespace(self) -> None:
        """Test getting PIN teams with whitespace handling."""
        self.preferences.activation_pin = ' LAL , GSW , BOS '
        self.preferences.save()
        
        teams = self.preferences.get_pin_teams()
        self.assertEqual(teams, ['LAL', 'GSW', 'BOS'])

    def test_set_pin_teams(self) -> None:
        """Test setting PIN teams from a list."""
        teams = ['LAL', 'GSW', 'BOS']
        self.preferences.set_pin_teams(teams)
        
        self.assertEqual(self.preferences.activation_pin, 'LAL,GSW,BOS')

    def test_set_pin_teams_with_whitespace(self) -> None:
        """Test setting PIN teams with whitespace handling."""
        teams = [' LAL ', ' GSW ', ' BOS ']
        self.preferences.set_pin_teams(teams)
        
        self.assertEqual(self.preferences.activation_pin, 'LAL,GSW,BOS')

    def test_set_pin_teams_filters_empty(self) -> None:
        """Test setting PIN teams filters out empty strings."""
        teams = ['LAL', '', 'GSW', '   ', 'BOS']
        self.preferences.set_pin_teams(teams)
        
        self.assertEqual(self.preferences.activation_pin, 'LAL,GSW,BOS')

    def test_validate_pin_correct(self) -> None:
        """Test PIN validation with correct teams."""
        self.preferences.activation_pin = 'LAL,GSW,BOS'
        self.preferences.save()
        
        submitted_teams = ['LAL', 'GSW', 'BOS']
        self.assertTrue(self.preferences.validate_pin(submitted_teams))

    def test_validate_pin_different_order(self) -> None:
        """Test PIN validation with teams in different order."""
        self.preferences.activation_pin = 'LAL,GSW,BOS'
        self.preferences.save()
        
        submitted_teams = ['BOS', 'LAL', 'GSW']
        self.assertTrue(self.preferences.validate_pin(submitted_teams))

    def test_validate_pin_incorrect(self) -> None:
        """Test PIN validation with incorrect teams."""
        self.preferences.activation_pin = 'LAL,GSW,BOS'
        self.preferences.save()
        
        submitted_teams = ['LAL', 'GSW', 'MIA']
        self.assertFalse(self.preferences.validate_pin(submitted_teams))

    def test_validate_pin_wrong_count(self) -> None:
        """Test PIN validation with wrong number of teams."""
        self.preferences.activation_pin = 'LAL,GSW,BOS'
        self.preferences.save()
        
        submitted_teams = ['LAL', 'GSW']
        self.assertFalse(self.preferences.validate_pin(submitted_teams))

    def test_validate_pin_with_whitespace(self) -> None:
        """Test PIN validation with whitespace in submitted teams."""
        self.preferences.activation_pin = 'LAL,GSW,BOS'
        self.preferences.save()
        
        submitted_teams = [' LAL ', ' GSW ', ' BOS ']
        self.assertTrue(self.preferences.validate_pin(submitted_teams))

    def test_validate_pin_case_insensitive(self) -> None:
        """Test PIN validation is case insensitive."""
        self.preferences.activation_pin = 'LAL,GSW,BOS'
        self.preferences.save()
        
        submitted_teams = ['lal', 'gsw', 'bos']
        self.assertTrue(self.preferences.validate_pin(submitted_teams))

    def test_validate_pin_no_pin_set(self) -> None:
        """Test PIN validation when no PIN is set."""
        self.preferences.activation_pin = ''
        self.preferences.save()
        
        submitted_teams = ['LAL', 'GSW', 'BOS']
        self.assertFalse(self.preferences.validate_pin(submitted_teams))
