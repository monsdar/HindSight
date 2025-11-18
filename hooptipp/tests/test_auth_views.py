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
    
    def test_signup_page_loads(self):
        """Test that the signup page loads correctly."""
        response = self.client.get(self.signup_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Account')
    
    def test_successful_signup(self):
        """Test successful user registration."""
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'securepassword123',
            'password2': 'securepassword123',
            'nickname': 'New User',
        }
        response = self.client.post(self.signup_url, data)
        
        # Should redirect to home after successful signup
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('predictions:home'))
        
        # User should be created
        self.assertTrue(User.objects.filter(username='newuser').exists())
        
        # User preferences should be created
        user = User.objects.get(username='newuser')
        self.assertTrue(UserPreferences.objects.filter(user=user).exists())
        prefs = UserPreferences.objects.get(user=user)
        self.assertEqual(prefs.nickname, 'New User')
        
        # User should be logged in
        user = User.objects.get(username='newuser')
        self.assertTrue(user.is_authenticated)
    
    def test_signup_with_missing_fields(self):
        """Test signup with missing required fields."""
        data = {
            'username': 'testuser',
            # Missing email, passwords
        }
        response = self.client.post(self.signup_url, data)
        
        # Should show errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email is required')
        self.assertContains(response, 'Password is required')
        
        # User should not be created
        self.assertFalse(User.objects.filter(username='testuser').exists())
    
    def test_signup_with_mismatched_passwords(self):
        """Test signup with mismatched passwords."""
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'password123',
            'password2': 'different456',
        }
        response = self.client.post(self.signup_url, data)
        
        # Should show error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Passwords do not match')
        
        # User should not be created
        self.assertFalse(User.objects.filter(username='testuser').exists())
    
    def test_signup_with_short_password(self):
        """Test signup with password that's too short."""
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'short',
            'password2': 'short',
        }
        response = self.client.post(self.signup_url, data)
        
        # Should show error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'at least 8 characters')
        
        # User should not be created
        self.assertFalse(User.objects.filter(username='testuser').exists())
    
    def test_signup_with_duplicate_username(self):
        """Test signup with a username that already exists."""
        # Create existing user
        User.objects.create_user(username='existinguser', email='existing@example.com', password='pass123')
        
        data = {
            'username': 'existinguser',
            'email': 'different@example.com',
            'password1': 'password123',
            'password2': 'password123',
        }
        response = self.client.post(self.signup_url, data)
        
        # Should show error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Username already exists')
    
    def test_signup_with_duplicate_email(self):
        """Test signup with an email that already exists."""
        # Create existing user
        User.objects.create_user(username='existinguser', email='existing@example.com', password='pass123')
        
        data = {
            'username': 'newuser',
            'email': 'existing@example.com',
            'password1': 'password123',
            'password2': 'password123',
        }
        response = self.client.post(self.signup_url, data)
        
        # Should show error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email already exists')


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

