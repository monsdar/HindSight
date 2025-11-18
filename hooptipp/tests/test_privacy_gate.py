"""Tests for privacy gate functionality."""

from django.test import TestCase, RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.messages import get_messages
from django.urls import reverse
from django.conf import settings
from unittest.mock import patch

from hooptipp.middleware import PrivacyGateMiddleware
from hooptipp.views import privacy_gate
from hooptipp.predictions.models import Option, OptionCategory


class PrivacyGateMiddlewareTests(TestCase):
    """Tests for PrivacyGateMiddleware."""

    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = PrivacyGateMiddleware(lambda r: None)

    def test_middleware_allows_admin_access(self):
        """Middleware should allow access to admin paths."""
        request = self.factory.get('/admin/')
        request.session = {}
        
        response = self.middleware(request)
        self.assertIsNone(response)  # No redirect

    def test_middleware_allows_health_endpoint(self):
        """Middleware should allow access to health endpoint."""
        request = self.factory.get('/health/')
        request.session = {}
        
        response = self.middleware(request)
        self.assertIsNone(response)  # No redirect

    def test_middleware_allows_robots_txt(self):
        """Middleware should allow access to robots.txt."""
        request = self.factory.get('/robots.txt')
        request.session = {}
        
        response = self.middleware(request)
        self.assertIsNone(response)  # No redirect

    def test_middleware_allows_privacy_gate_access(self):
        """Middleware should allow access to privacy gate itself."""
        request = self.factory.get('/privacy-gate/')
        request.session = {}
        
        response = self.middleware(request)
        self.assertIsNone(response)  # No redirect

    def test_middleware_allows_static_files(self):
        """Middleware should allow access to static files."""
        request = self.factory.get('/static/css/style.css')
        request.session = {}
        
        response = self.middleware(request)
        self.assertIsNone(response)  # No redirect

    @patch.object(settings, 'TESTING', False)
    @patch.object(settings, 'PRIVACY_GATE_ENABLED', True)
    @patch.object(settings, 'ENABLE_USER_SELECTION', True)
    def test_middleware_redirects_without_session(self):
        """Middleware should redirect to privacy gate without session."""
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.get('/')
        request.session = {}
        request.user = AnonymousUser()
        
        response = self.middleware(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/privacy-gate/')

    def test_middleware_allows_with_session(self):
        """Middleware should allow access with valid session."""
        request = self.factory.get('/')
        request.session = {'privacy_gate_passed': True}
        
        response = self.middleware(request)
        self.assertIsNone(response)  # No redirect

    @patch.object(settings, 'PRIVACY_GATE_ENABLED', False)
    def test_middleware_disabled_in_settings(self):
        """Middleware should be disabled when PRIVACY_GATE_ENABLED is False."""
        request = self.factory.get('/')
        request.session = {}
        
        response = self.middleware(request)
        self.assertIsNone(response)  # No redirect


class PrivacyGateViewTests(TestCase):
    """Tests for privacy gate view."""

    def setUp(self):
        # Create NBA teams category and some test teams
        self.teams_cat = OptionCategory.objects.create(
            slug='nba-teams',
            name='NBA Teams',
            description='National Basketball Association teams',
            icon='basketball',
            sort_order=10,
        )
        
        # Create test teams
        self.lakers = Option.objects.create(
            category=self.teams_cat,
            slug='lakers',
            name='Los Angeles Lakers',
            short_name='LAL',
            external_id='14',
            is_active=True,
        )
        
        self.celtics = Option.objects.create(
            category=self.teams_cat,
            slug='celtics',
            name='Boston Celtics',
            short_name='BOS',
            external_id='2',
            is_active=True,
        )
        
        self.warriors = Option.objects.create(
            category=self.teams_cat,
            slug='warriors',
            name='Golden State Warriors',
            short_name='GSW',
            external_id='10',
            is_active=True,
        )
        
        self.bulls = Option.objects.create(
            category=self.teams_cat,
            slug='bulls',
            name='Chicago Bulls',
            short_name='CHI',
            external_id='5',
            is_active=True,
        )
        
        # Add the additional teams needed for the new correct answer
        self.heat = Option.objects.create(
            category=self.teams_cat,
            slug='heat',
            name='Miami Heat',
            short_name='MIA',
            external_id='16',
            is_active=True,
        )
        
        self.kings = Option.objects.create(
            category=self.teams_cat,
            slug='kings',
            name='Sacramento Kings',
            short_name='SAC',
            external_id='26',
            is_active=True,
        )
        
        self.raptors = Option.objects.create(
            category=self.teams_cat,
            slug='raptors',
            name='Toronto Raptors',
            short_name='TOR',
            external_id='28',
            is_active=True,
        )
        
        self.suns = Option.objects.create(
            category=self.teams_cat,
            slug='suns',
            name='Phoenix Suns',
            short_name='PHX',
            external_id='24',
            is_active=True,
        )
        
        # Add the teams for the actual correct answer
        self.magic = Option.objects.create(
            category=self.teams_cat,
            slug='magic',
            name='Orlando Magic',
            short_name='ORL',
            external_id='22',
            is_active=True,
        )
        
        self.thunder = Option.objects.create(
            category=self.teams_cat,
            slug='thunder',
            name='Oklahoma City Thunder',
            short_name='OKC',
            external_id='21',
            is_active=True,
        )

    def test_privacy_gate_get_request(self):
        """Privacy gate should display team selection form on GET request."""
        response = self.client.get('/privacy-gate/')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'NBA Team Challenge')
        self.assertContains(response, 'Select the correct NBA teams to continue:')
        self.assertContains(response, 'LAL')
        self.assertContains(response, 'BOS')
        self.assertContains(response, 'GSW')
        self.assertContains(response, 'CHI')

    def test_privacy_gate_correct_answer(self):
        """Privacy gate should accept correct team selection."""
        response = self.client.post('/privacy-gate/', {
            'selected_teams': ['ORL', 'GSW', 'BOS', 'OKC']
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        
        # Check that session is set
        self.assertTrue(self.client.session.get('privacy_gate_passed'))

    def test_privacy_gate_incorrect_answer(self):
        """Privacy gate should reject incorrect team selection."""
        response = self.client.post('/privacy-gate/', {
            'selected_teams': ['LAL', 'BOS', 'GSW', 'MIA']  # Wrong team
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incorrect selection')
        
        # Check that session is not set
        self.assertFalse(self.client.session.get('privacy_gate_passed'))

    def test_privacy_gate_partial_answer(self):
        """Privacy gate should reject partial team selection."""
        response = self.client.post('/privacy-gate/', {
            'selected_teams': ['LAL', 'BOS']  # Only 2 teams
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incorrect selection')
        
        # Check that session is not set
        self.assertFalse(self.client.session.get('privacy_gate_passed'))

    def test_privacy_gate_extra_teams(self):
        """Privacy gate should reject selection with extra teams."""
        response = self.client.post('/privacy-gate/', {
            'selected_teams': ['LAL', 'BOS', 'GSW', 'CHI', 'MIA']  # 5 teams
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incorrect selection')
        
        # Check that session is not set
        self.assertFalse(self.client.session.get('privacy_gate_passed'))

    @patch.object(settings, 'PRIVACY_GATE_CORRECT_ANSWER', ['LAL', 'BOS'])
    def test_privacy_gate_custom_answer(self):
        """Privacy gate should use custom answer from settings."""
        response = self.client.post('/privacy-gate/', {
            'selected_teams': ['LAL', 'BOS']
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        
        # Check that session is set
        self.assertTrue(self.client.session.get('privacy_gate_passed'))

    def test_privacy_gate_team_logos_displayed(self):
        """Privacy gate should display team logos."""
        response = self.client.get('/privacy-gate/')
        
        self.assertEqual(response.status_code, 200)
        # Check that logo URLs are present in the response
        # Logos can be either local static files or CDN URLs
        response_content = response.content.decode('utf-8')
        has_local_logos = '/static/nba/logos/' in response_content
        has_cdn_logos = 'cdn.nba.com' in response_content
        self.assertTrue(has_local_logos or has_cdn_logos, 
                       "Response should contain either local logo paths (/static/nba/logos/) or CDN URLs (cdn.nba.com)")
        self.assertContains(response, '.svg')

    def test_privacy_gate_redirects_to_admin_when_no_teams(self):
        """Privacy gate should redirect to admin when no NBA teams are available."""
        # Delete all teams
        Option.objects.filter(category__slug='nba-teams').delete()
        
        response = self.client.get('/privacy-gate/')
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/admin/')


class PrivacyGateIntegrationTests(TestCase):
    """Integration tests for privacy gate functionality."""

    def setUp(self):
        # Create NBA teams category and test teams
        self.teams_cat = OptionCategory.objects.create(
            slug='nba-teams',
            name='NBA Teams',
            description='National Basketball Association teams',
            icon='basketball',
            sort_order=10,
        )
        
        # Create test teams
        Option.objects.create(
            category=self.teams_cat,
            slug='lakers',
            name='Los Angeles Lakers',
            short_name='LAL',
            external_id='14',
            is_active=True,
        )
        
        Option.objects.create(
            category=self.teams_cat,
            slug='celtics',
            name='Boston Celtics',
            short_name='BOS',
            external_id='2',
            is_active=True,
        )

    @patch.object(settings, 'TESTING', False)
    @patch.object(settings, 'PRIVACY_GATE_ENABLED', True)
    @patch.object(settings, 'ENABLE_USER_SELECTION', True)
    def test_full_privacy_gate_flow(self):
        """Test complete privacy gate flow from access to success."""
        # First, try to access main page without passing gate
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/privacy-gate/')
        
        # Access privacy gate
        response = self.client.get('/privacy-gate/')
        self.assertEqual(response.status_code, 200)
        
        # Submit correct answer
        response = self.client.post('/privacy-gate/', {
            'selected_teams': ['ORL', 'GSW', 'BOS', 'OKC']
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        
        # Now should be able to access main page
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_privacy_gate_persists_across_requests(self):
        """Test that privacy gate session persists across requests."""
        # Pass the privacy gate
        response = self.client.post('/privacy-gate/', {
            'selected_teams': ['ORL', 'GSW', 'BOS', 'OKC']
        })
        self.assertEqual(response.status_code, 302)
        
        # Make multiple requests to different pages
        response1 = self.client.get('/')
        response2 = self.client.get('/')
        
        # Both should succeed
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)
