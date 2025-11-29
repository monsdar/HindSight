"""Email verification utilities for HindSight.

Provides functions for generating verification tokens, sending verification emails,
and verifying email tokens to activate user accounts.
"""

from datetime import timedelta
from typing import Optional, Tuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

# Token expiry: 3 days (259200 seconds)
EMAIL_VERIFICATION_TIMEOUT = 259200


def generate_verification_token(user) -> str:
    """
    Generate a verification token for a user.
    
    Args:
        user: User instance to generate token for
        
    Returns:
        Token string (base64 encoded)
    """
    return default_token_generator.make_token(user)


def send_verification_email(user, request=None) -> None:
    """
    Send email verification email to user.
    
    Args:
        user: User instance to send verification email to
        request: Optional HttpRequest object for building absolute URLs
    """
    token = generate_verification_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    
    # Build verification URL
    if request:
        protocol = 'https' if request.is_secure() else 'http'
        domain = request.get_host()
        verification_url = f"{protocol}://{domain}{reverse('verify_email', args=[uid, token])}"
    else:
        # Fallback if no request available (e.g., in management commands)
        # Use first allowed host or default to localhost
        host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'
        protocol = 'https' if not host.startswith(('localhost', '127.0.0.1', '0.0.0.0')) else 'http'
        verification_url = f"{protocol}://{host}{reverse('verify_email', args=[uid, token])}"
    
    # Get site name from settings
    site_name = getattr(settings, 'PAGE_TITLE', 'HindSight')
    
    # Email subject
    subject = f'Verify your {site_name} account'
    
    # Render email templates
    context = {
        'user': user,
        'verification_url': verification_url,
        'site_name': site_name,
        'expiry_days': 3,  # 3 days expiry
    }
    
    html_message = render_to_string('emails/verification_email.html', context)
    plain_message = render_to_string('emails/verification_email.txt', context)
    
    # Send email
    from_email = settings.DEFAULT_FROM_EMAIL
    send_mail(
        subject=subject,
        message=plain_message,
        from_email=from_email,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )


def verify_email_token(uidb64: str, token: str) -> Tuple[bool, Optional[object], str]:
    """
    Verify email verification token and activate user account.
    
    Args:
        uidb64: Base64-encoded user ID
        token: Verification token
        
    Returns:
        Tuple of (success: bool, user: Optional[User], message: str)
    """
    User = get_user_model()
    
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user is None:
        return False, None, 'Invalid verification link. Please request a new verification email.'
    
    # Check if user is already verified
    if user.is_active:
        return True, user, 'Your email is already verified. You can log in now.'
    
    # Verify token
    if not default_token_generator.check_token(user, token):
        return False, user, 'Invalid or expired verification link. Please request a new verification email.'
    
    # Activate user
    user.is_active = True
    user.save(update_fields=['is_active'])
    
    return True, user, 'Your email has been verified successfully. You can now log in.'


def is_verification_token_valid(uidb64: str, token: str) -> bool:
    """
    Check if a verification token is valid without activating the user.
    
    Args:
        uidb64: Base64-encoded user ID
        token: Verification token
        
    Returns:
        True if token is valid, False otherwise
    """
    User = get_user_model()
    
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return False
    
    return default_token_generator.check_token(user, token)

