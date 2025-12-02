"""Tests for authentication views."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core import mail
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
        """Test successful user registration with email verification."""
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'securepassword123',
            'password2': 'securepassword123',
            'nickname': 'New User',
        }
        response = self.client.post(self.signup_url, data)
        
        # Should redirect to verify_email_sent page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('verify_email_sent'))
        
        # User should be created but inactive
        self.assertTrue(User.objects.filter(username='newuser').exists())
        user = User.objects.get(username='newuser')
        self.assertFalse(user.is_active)  # User should be inactive until verified
        
        # User preferences should be created
        self.assertTrue(UserPreferences.objects.filter(user=user).exists())
        prefs = UserPreferences.objects.get(user=user)
        self.assertEqual(prefs.nickname, 'New User')
        
        # User should NOT be logged in (must verify email first)
        self.assertNotIn('_auth_user_id', self.client.session)
    
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
            password='testpass123',
            is_active=True  # Active user for normal login tests
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
    
    def test_login_blocked_for_unverified_user(self):
        """Test that unverified (inactive) users cannot log in."""
        # Create an inactive (unverified) user
        inactive_user = User.objects.create_user(
            username='unverified',
            email='unverified@example.com',
            password='testpass123',
            is_active=False  # User hasn't verified email
        )
        
        data = {
            'username': 'unverified',
            'password': 'testpass123',
        }
        response = self.client.post(self.login_url, data)
        
        # Should stay on login page (form invalid)
        self.assertEqual(response.status_code, 200)
        
        # User should not be logged in
        self.assertNotIn('_auth_user_id', self.client.session)
        
        # Verify the form was invalid (user exists but is inactive)
        # The form should have been rejected, preventing login
        self.assertTrue(User.objects.filter(username='unverified', is_active=False).exists())


@override_settings(ENABLE_USER_SELECTION=False, PRIVACY_GATE_ENABLED=False)
class PasswordResetViewTests(TestCase):
    """Tests for password reset functionality."""
    
    def setUp(self):
        self.client = Client()
        self.password_reset_url = reverse('password_reset')
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_active=True
        )
    
    def test_password_reset_page_loads(self):
        """Test that the password reset page loads correctly."""
        response = self.client.get(self.password_reset_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reset Password')
    
    def test_password_reset_sends_email(self):
        """Test that password reset sends an email to the user."""
        # Clear mail outbox
        mail.outbox = []
        
        data = {
            'email': 'test@example.com',
        }
        response = self.client.post(self.password_reset_url, data)
        
        # Should redirect to done page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('password_reset_done'))
        
        # Email should be sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['test@example.com'])
        self.assertIn('Password Reset', mail.outbox[0].subject)
        self.assertIn('reset', mail.outbox[0].body.lower())
    
    def test_password_reset_with_nonexistent_email(self):
        """Test password reset with email that doesn't exist."""
        # Clear mail outbox
        mail.outbox = []
        
        data = {
            'email': 'nonexistent@example.com',
        }
        response = self.client.post(self.password_reset_url, data)
        
        # Should still redirect to done page (security: don't reveal if email exists)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('password_reset_done'))
        
        # No email should be sent
        self.assertEqual(len(mail.outbox), 0)
    
    def test_password_reset_with_inactive_user(self):
        """Test password reset with inactive (unverified) user."""
        # Create inactive user
        inactive_user = User.objects.create_user(
            username='inactive',
            email='inactive@example.com',
            password='testpass123',
            is_active=False
        )
        
        # Clear mail outbox
        mail.outbox = []
        
        data = {
            'email': 'inactive@example.com',
        }
        response = self.client.post(self.password_reset_url, data)
        
        # Should redirect to done page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('password_reset_done'))
        
        # No email should be sent (only active users can reset password)
        self.assertEqual(len(mail.outbox), 0)
    
    def test_password_reset_email_contains_reset_link(self):
        """Test that password reset email contains a valid reset link."""
        # Clear mail outbox
        mail.outbox = []
        
        data = {
            'email': 'test@example.com',
        }
        self.client.post(self.password_reset_url, data)
        
        # Check email content
        self.assertEqual(len(mail.outbox), 1)
        email_body = mail.outbox[0].body
        
        # Should contain reset URL pattern
        self.assertIn('password-reset-confirm', email_body)
        self.assertIn('http://testserver/password-reset-confirm/', email_body)
        
        # Check HTML email if present
        if mail.outbox[0].alternatives:
            html_body = mail.outbox[0].alternatives[0][0]
            self.assertIn('password-reset-confirm', html_body)
            self.assertIn('Reset Password', html_body)

