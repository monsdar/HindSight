"""Tests for user context handling in both authentication modes."""

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory, override_settings
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


@override_settings(ENABLE_USER_SELECTION=True)
class UserSelectionModeTests(UserContextTestCase):
    """Tests for user selection mode (family-friendly activation)."""
    
    def test_get_active_user_returns_none_when_no_session(self):
        """Test that get_active_user returns None when no user is in session."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = AnonymousUser()
        
        active_user = get_active_user(request)
        self.assertIsNone(active_user)
    
    def test_get_active_user_returns_user_from_session(self):
        """Test that get_active_user returns the user stored in session."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = AnonymousUser()
        request.session['active_user_id'] = self.user1.id
        
        active_user = get_active_user(request)
        self.assertEqual(active_user, self.user1)
    
    def test_get_active_user_handles_invalid_user_id(self):
        """Test that get_active_user handles invalid user IDs gracefully."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = AnonymousUser()
        request.session['active_user_id'] = 99999  # Non-existent user
        
        active_user = get_active_user(request)
        self.assertIsNone(active_user)
        # Session should be cleaned up
        self.assertNotIn('active_user_id', request.session)
    
    def test_set_active_user_stores_in_session(self):
        """Test that set_active_user stores user ID in session."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = AnonymousUser()
        
        set_active_user(request, self.user1)
        self.assertEqual(request.session['active_user_id'], self.user1.id)
    
    def test_clear_active_user_removes_from_session(self):
        """Test that clear_active_user removes user from session."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = AnonymousUser()
        request.session['active_user_id'] = self.user1.id
        
        clear_active_user(request)
        self.assertNotIn('active_user_id', request.session)
    
    def test_is_user_active_returns_true_when_user_in_session(self):
        """Test that is_user_active returns True when user is in session."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = AnonymousUser()
        request.session['active_user_id'] = self.user1.id
        
        self.assertTrue(is_user_active(request))
    
    def test_is_user_active_returns_false_when_no_user(self):
        """Test that is_user_active returns False when no user is active."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = AnonymousUser()
        
        self.assertFalse(is_user_active(request))


@override_settings(ENABLE_USER_SELECTION=False)
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
    
    def test_get_active_user_ignores_session(self):
        """Test that get_active_user ignores session in auth mode."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = self.user1
        request.session['active_user_id'] = self.user2.id  # Should be ignored
        
        active_user = get_active_user(request)
        self.assertEqual(active_user, self.user1)  # Should return authenticated user
    
    def test_set_active_user_does_not_store_in_session(self):
        """Test that set_active_user doesn't store in session in auth mode."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = self.user1
        
        set_active_user(request, self.user2)
        self.assertNotIn('active_user_id', request.session)
    
    def test_clear_active_user_does_not_affect_session(self):
        """Test that clear_active_user doesn't affect session in auth mode."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        request.user = self.user1
        request.session['active_user_id'] = self.user1.id
        
        clear_active_user(request)
        # Session should not be modified in auth mode
        self.assertEqual(request.session.get('active_user_id'), self.user1.id)
    
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


class UserContextSwitchModeTests(UserContextTestCase):
    """Tests for switching between modes."""
    
    def test_context_works_correctly_after_mode_switch(self):
        """Test that context works correctly when switching modes."""
        request = self.factory.get('/')
        request = self._add_session_to_request(request)
        
        # Start in user selection mode
        with override_settings(ENABLE_USER_SELECTION=True):
            request.user = AnonymousUser()
            set_active_user(request, self.user1)
            self.assertEqual(get_active_user(request), self.user1)
        
        # Switch to authentication mode
        with override_settings(ENABLE_USER_SELECTION=False):
            request.user = self.user2
            active_user = get_active_user(request)
            # Should now return the authenticated user, not session user
            self.assertEqual(active_user, self.user2)

