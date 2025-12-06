"""Tests for email verification functionality."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, Client, override_settings, RequestFactory
from django.urls import reverse

from hooptipp.email_verification import (
    generate_verification_token,
    send_verification_email,
    verify_email_token,
    is_verification_token_valid,
)


User = get_user_model()


@override_settings(ENABLE_USER_SELECTION=False, PRIVACY_GATE_ENABLED=False)
class EmailVerificationUtilsTests(TestCase):
    """Tests for email verification utility functions."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_active=False
        )
    
    def test_generate_verification_token(self):
        """Test that verification tokens can be generated."""
        token = generate_verification_token(self.user)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)
    
    def test_send_verification_email(self):
        """Test that verification email is sent correctly."""
        request_factory = RequestFactory()
        request = request_factory.get('/')
        
        send_verification_email(self.user, request)
        
        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        
        # Check email properties
        self.assertEqual(email.to, [self.user.email])
        self.assertIn('Verify', email.subject)
        self.assertIn(self.user.username, email.body)
        self.assertIn('verification', email.body.lower())
    
    def test_verify_email_token_valid(self):
        """Test verifying a valid email token."""
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        
        token = default_token_generator.make_token(self.user)
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        
        success, user, message = verify_email_token(uidb64, token)
        
        self.assertTrue(success)
        self.assertEqual(user, self.user)
        self.assertIn('verified', message.lower())
        
        # User should now be active
        user.refresh_from_db()
        self.assertTrue(user.is_active)
    
    def test_verify_email_token_invalid_token(self):
        """Test verifying with an invalid token."""
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        invalid_token = 'invalid-token-123'
        
        success, user, message = verify_email_token(uidb64, invalid_token)
        
        self.assertFalse(success)
        self.assertEqual(user, self.user)
        self.assertIn('invalid', message.lower())
        
        # User should still be inactive
        user.refresh_from_db()
        self.assertFalse(user.is_active)
    
    def test_verify_email_token_invalid_uid(self):
        """Test verifying with an invalid user ID."""
        from django.contrib.auth.tokens import default_token_generator
        
        token = default_token_generator.make_token(self.user)
        invalid_uidb64 = 'invalid-uid'
        
        success, user, message = verify_email_token(invalid_uidb64, token)
        
        self.assertFalse(success)
        self.assertIsNone(user)
        self.assertIn('invalid', message.lower())
    
    def test_verify_email_token_already_verified(self):
        """Test verifying an already verified user (idempotent)."""
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        
        # Activate user first
        self.user.is_active = True
        self.user.save()
        
        token = default_token_generator.make_token(self.user)
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        
        success, user, message = verify_email_token(uidb64, token)
        
        # Should return success (idempotent)
        self.assertTrue(success)
        self.assertEqual(user, self.user)
        self.assertIn('already verified', message.lower())
        
        # User should still be active
        user.refresh_from_db()
        self.assertTrue(user.is_active)
    
    def test_is_verification_token_valid(self):
        """Test checking if a token is valid without activating."""
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        
        token = default_token_generator.make_token(self.user)
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        
        # Token should be valid
        self.assertTrue(is_verification_token_valid(uidb64, token))
        
        # User should still be inactive (check doesn't activate)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
    
    def test_is_verification_token_valid_invalid(self):
        """Test checking an invalid token."""
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        invalid_token = 'invalid-token'
        
        self.assertFalse(is_verification_token_valid(uidb64, invalid_token))


@override_settings(ENABLE_USER_SELECTION=False, PRIVACY_GATE_ENABLED=False)
class EmailVerificationViewsTests(TestCase):
    """Tests for email verification views."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_active=False
        )
    
    def test_verify_email_sent_page(self):
        """Test that verify_email_sent page loads."""
        url = reverse('verify_email_sent')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Check Your Email')
    
    def test_verify_email_success(self):
        """Test successful email verification."""
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        
        token = default_token_generator.make_token(self.user)
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        
        url = reverse('verify_email', args=[uidb64, token])
        response = self.client.get(url)
        
        # Should redirect to success page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('verify_email_success'))
        
        # User should now be active
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
    
    def test_verify_email_failed(self):
        """Test failed email verification."""
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        invalid_token = 'invalid-token'
        
        url = reverse('verify_email', args=[uidb64, invalid_token])
        response = self.client.get(url)
        
        # Should redirect to failed page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('verify_email_failed'))
        
        # User should still be inactive
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
    
    def test_verify_email_success_page(self):
        """Test that verify_email_success page loads."""
        url = reverse('verify_email_success')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email Verified')
    
    def test_verify_email_failed_page(self):
        """Test that verify_email_failed page loads."""
        url = reverse('verify_email_failed')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Verification Failed')
    
    def test_resend_verification_page_loads(self):
        """Test that resend verification page loads."""
        url = reverse('resend_verification')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Resend Verification Email')
    
    def test_resend_verification_success(self):
        """Test successful resend of verification email."""
        url = reverse('resend_verification')
        data = {'email': self.user.email}
        
        # Clear any existing emails and cache (to avoid rate limiting from other tests)
        mail.outbox.clear()
        cache.clear()
        
        response = self.client.post(url, data)
        
        # Should redirect to done page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('resend_verification_done'))
        
        # Email should be sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
    
    def test_resend_verification_nonexistent_email(self):
        """Test resend verification with non-existent email (security)."""
        url = reverse('resend_verification')
        data = {'email': 'nonexistent@example.com'}
        
        response = self.client.post(url, data)
        
        # Should still redirect to done page (don't reveal if email exists)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('resend_verification_done'))
        
        # No email should be sent
        self.assertEqual(len(mail.outbox), 0)
    
    def test_resend_verification_already_verified(self):
        """Test resend verification for already verified user."""
        self.user.is_active = True
        self.user.save()
        
        url = reverse('resend_verification')
        data = {'email': self.user.email}
        
        response = self.client.post(url, data)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))
    
    def test_resend_verification_rate_limiting(self):
        """Test rate limiting on resend verification."""
        url = reverse('resend_verification')
        data = {'email': self.user.email}
        
        # Clear cache
        cache.clear()
        
        # Send 3 requests (should be allowed)
        for i in range(3):
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 302)
        
        # 4th request should be rate limited
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Too many')
    
    def test_resend_verification_done_page(self):
        """Test that resend verification done page loads."""
        url = reverse('resend_verification_done')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Verification Email Sent')


@override_settings(ENABLE_USER_SELECTION=False, PRIVACY_GATE_ENABLED=False)
class EmailVerificationIntegrationTests(TestCase):
    """Integration tests for the full email verification flow."""
    
    def setUp(self):
        self.client = Client()
    
    def test_full_signup_and_verification_flow(self):
        """Test the complete flow: signup -> email -> verification -> login."""
        # Step 1: Sign up
        signup_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'securepass123',
            'password2': 'securepass123',
        }
        response = self.client.post(reverse('signup'), signup_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('verify_email_sent'))
        
        # User should be created but inactive
        user = User.objects.get(username='newuser')
        self.assertFalse(user.is_active)
        
        # Verification email should be sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [user.email])
        
        # Step 2: Extract verification token from email (in real scenario, user clicks link)
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        
        token = default_token_generator.make_token(user)
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        
        # Step 3: Verify email
        verify_url = reverse('verify_email', args=[uidb64, token])
        response = self.client.get(verify_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('verify_email_success'))
        
        # User should now be active
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        
        # Step 4: Login should now work
        login_data = {
            'username': 'newuser',
            'password': 'securepass123',
        }
        response = self.client.post(reverse('login'), login_data)
        self.assertEqual(response.status_code, 302)
        
        # User should be logged in
        self.assertIn('_auth_user_id', self.client.session)

