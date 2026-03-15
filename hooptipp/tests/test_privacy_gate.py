"""Tests for privacy gate functionality."""

from django.test import TestCase, RequestFactory
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from unittest.mock import patch

from hooptipp.middleware import PrivacyGateMiddleware


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

    def test_middleware_allows_static_files(self):
        """Middleware should allow access to static files."""
        request = self.factory.get('/static/css/style.css')
        request.session = {}
        
        response = self.middleware(request)
        self.assertIsNone(response)  # No redirect

    @patch.object(settings, 'TESTING', False)
    @patch.object(settings, 'PRIVACY_GATE_ENABLED', True)
    def test_middleware_redirects_anonymous_to_login_when_enabled(self):
        """Middleware should redirect anonymous users to login when enabled."""
        request = self.factory.get('/')
        request.session = {}
        request.user = AnonymousUser()

        response = self.middleware(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, settings.LOGIN_URL)

    @patch.object(settings, 'TESTING', False)
    @patch.object(settings, 'PRIVACY_GATE_ENABLED', True)
    def test_middleware_allows_authenticated_user_when_enabled(self):
        """Middleware should allow authenticated users when gate is enabled."""
        request = self.factory.get('/')
        request.session = {}
        user = User(username='testuser')
        user.is_authenticated = True
        request.user = user

        response = self.middleware(request)
        self.assertIsNone(response)

    @patch.object(settings, 'PRIVACY_GATE_ENABLED', False)
    def test_middleware_disabled_in_settings(self):
        """Middleware should be disabled when PRIVACY_GATE_ENABLED is False."""
        request = self.factory.get('/')
        request.session = {}
        
        response = self.middleware(request)
        self.assertIsNone(response)  # No redirect
class PrivacyGateIntegrationTests(TestCase):
    """Integration tests for privacy gate / login gate behavior."""

    @patch.object(settings, 'TESTING', False)
    @patch.object(settings, 'PRIVACY_GATE_ENABLED', True)
    def test_anonymous_user_is_redirected_to_login_and_authenticated_can_access(self):
        """Anonymous users are redirected to login; authenticated users see the main page."""
        # Anonymous access to main page should redirect to login
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, settings.LOGIN_URL)

        # Create and log in a user
        user = User.objects.create_user(username='testuser', password='password123')
        login_successful = self.client.login(username='testuser', password='password123')
        self.assertTrue(login_successful)

        # Authenticated user should see the main page
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
