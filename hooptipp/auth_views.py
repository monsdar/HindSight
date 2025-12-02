"""Authentication views for HindSight."""

import time
from typing import Optional

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import LoginView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.core.cache import cache
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.http import require_http_methods
from django.views.generic import FormView

from hooptipp.email_verification import send_verification_email, verify_email_token
from hooptipp.predictions.models import UserPreferences


@require_http_methods(["GET", "POST"])
def signup(request):
    """
    User registration view.
    
    Only available when ENABLE_USER_SELECTION is False (authentication mode).
    """
    # Redirect to home if in user selection mode
    if settings.ENABLE_USER_SELECTION:
        messages.info(request, 'User registration is not available in this mode. Please contact an administrator.')
        return redirect('predictions:home')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        nickname = request.POST.get('nickname', '').strip()
        
        # Validation
        errors = []
        
        if not username:
            errors.append('Username is required.')
        elif len(username) < 3:
            errors.append('Username must be at least 3 characters long.')
        
        if not email:
            errors.append('Email is required.')
        
        if not password1:
            errors.append('Password is required.')
        elif len(password1) < 8:
            errors.append('Password must be at least 8 characters long.')
        
        if password1 != password2:
            errors.append('Passwords do not match.')
        
        User = get_user_model()
        
        # Check if username exists
        if username and User.objects.filter(username=username).exists():
            errors.append('Username already exists.')
        
        # Check if email exists
        if email and User.objects.filter(email=email).exists():
            errors.append('Email already exists.')
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'auth/signup.html', {
                'username': username,
                'email': email,
                'nickname': nickname,
            })
        
        # Create user
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1,
                is_active=False  # User must verify email before activation
            )
            
            # Create user preferences
            UserPreferences.objects.create(
                user=user,
                nickname=nickname if nickname else ''
            )
            
            # Send verification email
            try:
                send_verification_email(user, request)
            except Exception as email_error:
                # If email fails, still create user but log error
                messages.warning(
                    request,
                    'Account created but verification email could not be sent. '
                    'Please contact support or try logging in to request a new verification email.'
                )
                # Log the error for debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f'Failed to send verification email to {email}: {str(email_error)}')
            
            # Don't log user in - they need to verify email first
            messages.success(
                request,
                f'Account created successfully! Please check your email ({email}) '
                'to verify your account before logging in.'
            )
            return redirect('verify_email_sent')
            
        except Exception as e:
            messages.error(request, f'An error occurred while creating your account: {str(e)}')
            return render(request, 'auth/signup.html', {
                'username': username,
                'email': email,
                'nickname': nickname,
            })
    
    return render(request, 'auth/signup.html')


@login_required
def profile(request):
    """
    User profile view.
    
    Allows users to update their preferences.
    Only available in authentication mode.
    """
    if settings.ENABLE_USER_SELECTION:
        messages.info(request, 'Profile editing is not available in this mode.')
        return redirect('predictions:home')
    
    # Redirect to home page - preferences editing is handled there
    return redirect('predictions:home')


def _check_rate_limit(email: str, action: str, max_attempts: int = 3, window_seconds: int = 3600) -> tuple[bool, Optional[int]]:
    """
    Check if an action is rate limited for a given email.
    
    Args:
        email: Email address to check
        action: Action identifier (e.g., 'resend_verification')
        max_attempts: Maximum number of attempts allowed
        window_seconds: Time window in seconds (default: 1 hour)
        
    Returns:
        Tuple of (is_allowed: bool, seconds_until_reset: Optional[int])
    """
    cache_key = f'rate_limit:{action}:{email}'
    attempts = cache.get(cache_key, 0)
    
    if attempts >= max_attempts:
        # Check when the window expires
        expire_time = cache.get(f'{cache_key}:expires', time.time() + window_seconds)
        seconds_remaining = int(expire_time - time.time())
        if seconds_remaining > 0:
            return False, seconds_remaining
        else:
            # Window expired, reset
            cache.delete(cache_key)
            cache.delete(f'{cache_key}:expires')
            attempts = 0
    
    # Increment attempts
    attempts += 1
    cache.set(cache_key, attempts, window_seconds)
    cache.set(f'{cache_key}:expires', time.time() + window_seconds, window_seconds)
    
    return True, None


def verify_email_sent(request):
    """Page shown after signup directing user to check email."""
    if settings.ENABLE_USER_SELECTION:
        return redirect('predictions:home')
    
    return render(request, 'auth/verify_email.html')


def verify_email(request, uidb64: str, token: str):
    """
    Verify email address using token from verification link.
    
    Args:
        uidb64: Base64-encoded user ID
        token: Verification token
    """
    if settings.ENABLE_USER_SELECTION:
        return redirect('predictions:home')
    
    success, user, message = verify_email_token(uidb64, token)
    
    if success:
        messages.success(request, message)
        return redirect('verify_email_success')
    else:
        messages.error(request, message)
        return redirect('verify_email_failed')


def verify_email_success(request):
    """Success page after email verification."""
    if settings.ENABLE_USER_SELECTION:
        return redirect('predictions:home')
    
    return render(request, 'auth/verify_email_success.html')


def verify_email_failed(request):
    """Error page for failed email verification."""
    if settings.ENABLE_USER_SELECTION:
        return redirect('predictions:home')
    
    return render(request, 'auth/verify_email_failed.html')


@require_http_methods(["GET", "POST"])
def resend_verification(request):
    """
    Resend verification email to user.
    
    Rate limited: max 3 requests per email per hour.
    """
    if settings.ENABLE_USER_SELECTION:
        return redirect('predictions:home')
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        
        if not email:
            messages.error(request, 'Email address is required.')
            return render(request, 'auth/resend_verification.html', {'email': ''})
        
        User = get_user_model()
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don't reveal if email exists or not (security best practice)
            messages.success(
                request,
                'If an account exists with that email address, '
                'a verification email has been sent.'
            )
            return redirect('resend_verification_done')
        
        # Check if user is already verified
        if user.is_active:
            messages.info(request, 'This account is already verified. You can log in now.')
            return redirect('login')
        
        # Check rate limit
        is_allowed, seconds_remaining = _check_rate_limit(
            email, 'resend_verification', max_attempts=3, window_seconds=3600
        )
        
        if not is_allowed:
            minutes_remaining = (seconds_remaining + 59) // 60  # Round up
            messages.error(
                request,
                f'Too many verification email requests. '
                f'Please try again in {minutes_remaining} minute{"s" if minutes_remaining != 1 else ""}.'
            )
            return render(request, 'auth/resend_verification.html', {'email': email})
        
        # Send verification email
        try:
            send_verification_email(user, request)
            messages.success(
                request,
                'If an account exists with that email address, '
                'a verification email has been sent.'
            )
        except Exception as e:
            messages.error(
                request,
                'An error occurred while sending the verification email. '
                'Please try again later or contact support.'
            )
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Failed to resend verification email to {email}: {str(e)}')
        
        return redirect('resend_verification_done')
    
    return render(request, 'auth/resend_verification.html')


def resend_verification_done(request):
    """Confirmation page after resending verification email."""
    if settings.ENABLE_USER_SELECTION:
        return redirect('predictions:home')
    
    return render(request, 'auth/resend_verification_done.html')


class CustomLoginView(LoginView):
    """Custom login view that blocks unverified users."""
    template_name = 'auth/login.html'
    
    def form_valid(self, form):
        """Check if user is active before allowing login."""
        user = form.get_user()
        
        if not user.is_active:
            # User account exists but is not verified
            messages.error(
                self.request,
                'Please verify your email address before logging in. '
                'Check your inbox for the verification link, or request a new verification email using the link below.'
            )
            return self.form_invalid(form)
        
        return super().form_valid(form)


class CustomPasswordResetView(FormView):
    """
    Custom password reset view with robust email handling.
    
    This view handles email sending errors gracefully and uses the same
    email sending method as the verification emails to ensure consistency.
    """
    template_name = 'auth/password_reset.html'
    form_class = PasswordResetForm
    email_template_name = 'emails/password_reset_email.html'
    subject_template_name = 'emails/password_reset_subject.txt'
    token_generator = default_token_generator
    
    def form_valid(self, form):
        """Process the password reset form and send email."""
        email = form.cleaned_data['email']
        User = get_user_model()
        
        # Get all users with this email (should be 0 or 1)
        active_users = User.objects.filter(email__iexact=email, is_active=True)
        
        # Don't reveal if email exists or not (security best practice)
        # Always show success message
        if active_users.exists():
            for user in active_users:
                try:
                    self._send_password_reset_email(user)
                except Exception as e:
                    # Log error but don't reveal to user
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f'Failed to send password reset email to {email}: {str(e)}')
                    # Still show success to user (security best practice)
        
        return redirect('password_reset_done')
    
    def _send_password_reset_email(self, user):
        """
        Send password reset email using the same robust method as verification emails.
        
        Args:
            user: User instance to send password reset email to
        """
        token = self.token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        # Build reset URL
        if self.request:
            protocol = 'https' if self.request.is_secure() else 'http'
            domain = self.request.get_host()
            reset_url = f"{protocol}://{domain}{reverse('password_reset_confirm', args=[uid, token])}"
        else:
            # Fallback if no request available
            host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'
            protocol = 'https' if not host.startswith(('localhost', '127.0.0.1', '0.0.0.0')) else 'http'
            reset_url = f"{protocol}://{host}{reverse('password_reset_confirm', args=[uid, token])}"
        
        # Get site name from settings
        site_name = getattr(settings, 'PAGE_TITLE', 'HindSight')
        
        # Render email subject
        subject = render_to_string(self.subject_template_name, {
            'site_name': site_name,
        }).strip()
        
        # Render email templates
        context = {
            'user': user,
            'reset_url': reset_url,
            'site_name': site_name,
            'uid': uid,
            'token': token,
        }
        
        html_message = render_to_string(self.email_template_name, context)
        plain_message = render_to_string('emails/password_reset_email.txt', context)
        
        # Send email using the same method as verification emails
        from_email = settings.DEFAULT_FROM_EMAIL
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    """
    Custom password reset confirm view that properly displays form errors.
    
    This view extends Django's PasswordResetConfirmView to ensure form errors
    are properly displayed in the template.
    """
    template_name = 'auth/password_reset_confirm.html'
    form_class = SetPasswordForm
    token_generator = default_token_generator
    post_reset_login = False
    post_reset_login_backend = None
    
    def get_success_url(self):
        """Return the URL to redirect to after successful password reset."""
        return reverse('password_reset_complete')
    
    def form_invalid(self, form):
        """Handle invalid form submission and display errors."""
        # Display form errors as messages
        for field, errors in form.errors.items():
            for error in errors:
                if field == '__all__':
                    messages.error(self.request, error)
                else:
                    # Field-specific errors
                    field_name = field.replace('_', ' ').title()
                    messages.error(self.request, f'{field_name}: {error}')
        
        # Return the form with errors (don't redirect)
        return self.render_to_response(self.get_context_data(form=form))
    
    def form_valid(self, form):
        """Handle valid form submission."""
        # Save the new password
        user = form.save()
        
        # Display success message
        messages.success(
            self.request,
            'Your password has been successfully reset. You can now log in with your new password.'
        )
        
        # Redirect to success page
        return redirect(self.get_success_url())

