"""Tests for page customization via environment variables."""

from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model


class PageCustomizationIntegrationTestCase(TestCase):
    """Integration tests for page title and slogan customization."""

    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.user = User.objects.create_user(username='testuser', password='testpass')

    @override_settings(
        PAGE_TITLE='HindSight',
        PAGE_SLOGAN="Find out who's always right!",
        PRIVACY_GATE_ENABLED=False
    )
    def test_default_title_and_slogan_in_home(self):
        """Test that default title and slogan appear in the home page."""
        response = self.client.get('/')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'HindSight')
        # Check for HTML-escaped version of the slogan
        self.assertContains(response, "Find out who&#x27;s always right!")
        # Check title tag
        self.assertContains(response, '<title>HindSight &ndash; Dashboard</title>')

    @override_settings(
        PAGE_TITLE='NBA Predictions',
        PAGE_SLOGAN='Who will win tonight?',
        PRIVACY_GATE_ENABLED=False
    )
    def test_custom_title_and_slogan_in_home(self):
        """Test that custom title and slogan appear in the home page."""
        response = self.client.get('/')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'NBA Predictions')
        self.assertContains(response, 'Who will win tonight?')
        # Check title tag
        self.assertContains(response, '<title>NBA Predictions &ndash; Dashboard</title>')

    @override_settings(
        PAGE_TITLE='Hoops Tips',
        PAGE_SLOGAN='Make your predictions count!',
        PRIVACY_GATE_ENABLED=False
    )
    def test_custom_title_in_navigation(self):
        """Test that custom title appears in the navigation bar."""
        response = self.client.get('/')
        
        self.assertEqual(response.status_code, 200)
        # Check that the title appears in the nav bar with theme-specific styling
        self.assertContains(response, 'class="text-2xl font-extrabold tracking-tight theme-accent-text">Hoops Tips</a>')
        self.assertContains(response, 'class="text-sm text-slate-400">Make your predictions count!</p>')

