"""Custom middleware for HindSight application."""

import logging
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class PrivacyGateMiddleware:
    """
    Middleware that enforces a privacy gate for accessing the application.
    
    Users must complete a simple NBA team selection challenge before accessing
    the main application. The challenge completion is stored in the session.
    
    This is only used in USER_SELECTION mode (ENABLE_USER_SELECTION=True).
    In AUTHENTICATION mode, users must login instead.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip privacy gate if disabled in settings
        if not getattr(settings, 'PRIVACY_GATE_ENABLED', True):
            return self.get_response(request)
        
        # Skip privacy gate if using authentication mode (users must login instead)
        if not getattr(settings, 'ENABLE_USER_SELECTION', True):
            return self.get_response(request)
            
        # Skip privacy gate in test mode
        if getattr(settings, 'TESTING', False):
            return self.get_response(request)
        
        # Skip privacy gate for authenticated users even in selection mode
        # This allows admins to bypass the gate
        if hasattr(request, 'user') and request.user.is_authenticated:
            return self.get_response(request)
            
        # Skip privacy gate check for these paths
        skip_paths = [
            '/admin/',
            '/health/',
            '/robots.txt',
            '/privacy-gate/',
            '/static/',
            '/media/',
            '/login/',
            '/logout/',
            '/signup/',
            '/password-reset/',
        ]
        
        # Check if current path should skip privacy gate
        if any(request.path.startswith(path) for path in skip_paths):
            logging.info(f"Skipping privacy gate for path {request.path}")
            return self.get_response(request)
            
        # Check if user has passed the privacy gate
        if not request.session.get('privacy_gate_passed', False):
            return redirect('privacy_gate')
            
        return self.get_response(request)
