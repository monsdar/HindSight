"""Tests for authentication views."""

from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from hooptipp.predictions.models import UserPreferences


User = get_user_model()


@override_settings(ENABLE_USER_SELECTION=False, PRIVACY_GATE_ENABLED=False)
class SignupViewTests(TestCase):
    """Tests for the signup view in authentication mode."""
    
    def setUp(self):
        self.client = Client()
        self.signup_url = reverse('signup')
    
    def test_signup_redirects_to_login(self):
        """Test that signup view redirects to login (OAuth-only signup)."""
        response = self.client.get(self.signup_url)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))
    
    def test_signup_post_redirects_to_login(self):
        """Test that POST to signup also redirects to login."""
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'securepassword123',
            'password2': 'securepassword123',
        }
        response = self.client.post(self.signup_url, data)
        
        # Should redirect to login (no new email/password signups)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))
        
        # User should NOT be created via signup form
        self.assertFalse(User.objects.filter(username='newuser').exists())


@override_settings(ENABLE_USER_SELECTION=True)
class SignupViewInSelectionModeTests(TestCase):
    """Tests for signup view when in user selection mode."""
    
    def setUp(self):
        self.client = Client()
        self.signup_url = reverse('signup')
    
    def test_signup_redirects_in_selection_mode(self):
        """Test that signup redirects when in user selection mode."""
        response = self.client.get(self.signup_url)
        
        # Should redirect to home
        self.assertEqual(response.status_code, 302)


@override_settings(ENABLE_USER_SELECTION=False, PRIVACY_GATE_ENABLED=False)
class LoginViewTests(TestCase):
    """Tests for login functionality in authentication mode."""
    
    def setUp(self):
        self.client = Client()
        self.login_url = reverse('login')
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_login_page_loads(self):
        """Test that the login page loads correctly."""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Login')
    
    def test_successful_login(self):
        """Test successful login."""
        data = {
            'username': 'testuser',
            'password': 'testpass123',
        }
        response = self.client.post(self.login_url, data)
        
        # Should redirect after login
        self.assertEqual(response.status_code, 302)
        
        # User should be logged in
        user = User.objects.get(username='testuser')
        # Check session
        self.assertIn('_auth_user_id', self.client.session)
    
    def test_login_with_wrong_password(self):
        """Test login with incorrect password."""
        data = {
            'username': 'testuser',
            'password': 'wrongpassword',
        }
        response = self.client.post(self.login_url, data)
        
        # Should stay on login page
        self.assertEqual(response.status_code, 200)
        
        # User should not be logged in
        self.assertNotIn('_auth_user_id', self.client.session)
    
    def test_logout(self):
        """Test logout functionality."""
        # Login first
        self.client.login(username='testuser', password='testpass123')
        self.assertIn('_auth_user_id', self.client.session)
        
        # Logout
        logout_url = reverse('logout')
        response = self.client.post(logout_url)
        
        # Should redirect
        self.assertEqual(response.status_code, 302)
        
        # Session should be cleared
        self.assertNotIn('_auth_user_id', self.client.session)

