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
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip privacy gate if disabled in settings
        if not getattr(settings, 'PRIVACY_GATE_ENABLED', True):
            return self.get_response(request)
            
        # Skip privacy gate in test mode
        if getattr(settings, 'TESTING', False):
            return self.get_response(request)
            
        # Skip privacy gate check for these paths
        skip_paths = [
            '/admin/',
            '/health/',
            '/robots.txt',
            '/privacy-gate/',
            '/static/',
            '/media/',
        ]
        
        # Check if current path should skip privacy gate
        if any(request.path.startswith(path) for path in skip_paths):
            logging.info(f"Skipping privacy gate for path {request.path}")
            return self.get_response(request)
            
        # Check if user has passed the privacy gate
        if not request.session.get('privacy_gate_passed', False):
            return redirect('privacy_gate')
            
        return self.get_response(request)
