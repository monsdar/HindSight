"""
Unified user context handling for HindSight.

Supports two deployment modes:
1. AUTHENTICATION mode (ENABLE_USER_SELECTION=False): Traditional login/signup
2. USER_SELECTION mode (ENABLE_USER_SELECTION=True): Family-friendly activation

This module provides a consistent interface for getting the active user
regardless of which mode the deployment is using.
"""

from functools import wraps
from typing import Optional

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest
from django.shortcuts import redirect


def get_active_user(request: HttpRequest):
    """
    Get the active user based on deployment mode.
    
    - In AUTHENTICATION mode: returns request.user if authenticated
    - In USER_SELECTION mode: returns user from session
    - Returns None if no user is active
    
    Args:
        request: The HTTP request object
        
    Returns:
        User instance or None
    """
    # Authentication mode - use Django's built-in auth
    if not settings.ENABLE_USER_SELECTION:
        return request.user if request.user.is_authenticated else None
    
    # User selection mode - use session-based activation
    user_id = request.session.get('active_user_id')
    if not user_id:
        return None
    
    User = get_user_model()
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        request.session.pop('active_user_id', None)
        return None


def set_active_user(request: HttpRequest, user) -> None:
    """
    Set the active user based on deployment mode.
    
    - In AUTHENTICATION mode: This is handled by Django's login
    - In USER_SELECTION mode: Store user ID in session
    
    Args:
        request: The HTTP request object
        user: The user to set as active
    """
    if settings.ENABLE_USER_SELECTION:
        request.session['active_user_id'] = user.id


def clear_active_user(request: HttpRequest) -> None:
    """
    Clear the active user based on deployment mode.
    
    - In AUTHENTICATION mode: This is handled by Django's logout
    - In USER_SELECTION mode: Remove user ID from session
    
    Args:
        request: The HTTP request object
    """
    if settings.ENABLE_USER_SELECTION:
        request.session.pop('active_user_id', None)


def requires_active_user(view_func):
    """
    Decorator that ensures a user is active in either mode.
    
    In AUTHENTICATION mode: Redirects to login if not authenticated
    In USER_SELECTION mode: Redirects to home with error message
    
    Usage:
        @requires_active_user
        def my_view(request):
            # request will have an active user here
            user = get_active_user(request)
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = get_active_user(request)
        if not user:
            if settings.ENABLE_USER_SELECTION:
                messages.error(request, 'Please select a user to continue.')
                return redirect('predictions:home')
            else:
                # Redirect to login in auth mode
                return redirect_to_login(request.get_full_path())
        return view_func(request, *args, **kwargs)
    
    return wrapper


def is_user_active(request: HttpRequest) -> bool:
    """
    Check if there's an active user in the current request.
    
    Args:
        request: The HTTP request object
        
    Returns:
        True if a user is active, False otherwise
    """
    return get_active_user(request) is not None

