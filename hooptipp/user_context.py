"""
User context handling for HindSight.

This module provides a consistent interface for getting the active user.
Uses Django's standard authentication system.
"""

from functools import wraps
from typing import Optional

from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest


def get_active_user(request: HttpRequest):
    """
    Get the active user from Django's authentication system.
    
    Returns request.user if authenticated, None otherwise.
    
    Args:
        request: The HTTP request object
        
    Returns:
        User instance or None
    """
    return request.user if request.user.is_authenticated else None


def set_active_user(request: HttpRequest, user) -> None:
    """
    Set the active user (no-op in authentication mode).
    
    In authentication mode, user activation is handled by Django's login().
    This function is kept for backward compatibility but does nothing.
    
    Args:
        request: The HTTP request object
        user: The user to set as active
    """
    pass


def clear_active_user(request: HttpRequest) -> None:
    """
    Clear the active user (no-op in authentication mode).
    
    In authentication mode, user deactivation is handled by Django's logout().
    This function is kept for backward compatibility but does nothing.
    
    Args:
        request: The HTTP request object
    """
    pass


def requires_active_user(view_func):
    """
    Decorator that ensures a user is authenticated.
    
    Redirects to login if not authenticated.
    
    Usage:
        @requires_active_user
        def my_view(request):
            # request will have an authenticated user here
            user = get_active_user(request)
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return view_func(request, *args, **kwargs)
    
    return wrapper


def is_user_active(request: HttpRequest) -> bool:
    """
    Check if there's an active (authenticated) user in the current request.
    
    Args:
        request: The HTTP request object
        
    Returns:
        True if a user is authenticated, False otherwise
    """
    return request.user.is_authenticated

