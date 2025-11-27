"""Authentication views for HindSight."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from hooptipp.predictions.models import UserPreferences


@require_http_methods(["GET", "POST"])
def signup(request):
    """
    User registration view - redirects to login.
    
    New user signup is only available via Google OAuth.
    This view redirects to login with a message explaining OAuth-only signup.
    Only available when ENABLE_USER_SELECTION is False (authentication mode).
    """
    # Redirect to home if in user selection mode
    if settings.ENABLE_USER_SELECTION:
        messages.info(request, 'User registration is not available in this mode. Please contact an administrator.')
        return redirect('predictions:home')
    
    # Redirect to login with message about OAuth-only signup
    messages.info(
        request,
        'New accounts are created automatically when you sign in with Google. Please use the Google sign-in button on the login page.'
    )
    return redirect('login')


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

