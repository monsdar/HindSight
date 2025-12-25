"""Tests for user context handling in authentication mode."""

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware

from hooptipp.user_context import (
    get_active_user,
    set_active_user,
    clear_active_user,
    is_user_active,
)


User = get_user_model()


class UserContextTestCase(TestCase):
    """Base test case with common setup for user context tests."""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.user1 = User.objects.create_user(username='testuser1', password='testpass123')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass123')
    
    def _add_session_to_request(self, request):
        """Add session support to a request."""
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()
        return request


class AuthenticationModeTests(UserContextTestCase):
    """Tests for authentication mode (standard login/signup)."""
    
    def test_get_active_user_returns_authenticated_user(self):
        """Test that get_active_user returns the authenticated user."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = self.user1
        
        active_user = get_active_user(request)
        self.assertEqual(active_user, self.user1)
    
    def test_get_active_user_returns_none_for_anonymous(self):
        """Test that get_active_user returns None for anonymous users."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = AnonymousUser()
        
        active_user = get_active_user(request)
        self.assertIsNone(active_user)
    
    def test_set_active_user_is_noop(self):
        """Test that set_active_user does nothing in auth mode."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = self.user1
        
        # Should not modify session
        set_active_user(request, self.user2)
        self.assertNotIn('active_user_id', request.session)
    
    def test_clear_active_user_is_noop(self):
        """Test that clear_active_user does nothing in auth mode."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = self.user1
        request.session['some_other_key'] = 'value'
        
        clear_active_user(request)
        # Should not affect session
        self.assertEqual(request.session.get('some_other_key'), 'value')
    
    def test_is_user_active_returns_true_for_authenticated(self):
        """Test that is_user_active returns True for authenticated users."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = self.user1
        
        self.assertTrue(is_user_active(request))
    
    def test_is_user_active_returns_false_for_anonymous(self):
        """Test that is_user_active returns False for anonymous users."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = AnonymousUser()
        
        self.assertFalse(is_user_active(request))

