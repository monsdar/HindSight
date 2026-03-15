"""Custom middleware for HindSight application."""

from django.conf import settings
from django.shortcuts import redirect


class PrivacyGateMiddleware:
    """
    Middleware that optionally enforces a simple privacy gate based on
    authentication status.

    - If PRIVACY_GATE_ENABLED is True and the user is not authenticated,
      only the login view is accessible.
    - If the user is authenticated or PRIVACY_GATE_ENABLED is not True,
      the request is passed through unchanged.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip privacy gate in test mode
        if getattr(settings, 'TESTING', False):
            return self.get_response(request)

        # Skip privacy gate entirely when disabled
        if not getattr(settings, 'PRIVACY_GATE_ENABLED', False):
            return self.get_response(request)

        # Allow authenticated users to access the site normally
        # AuthenticationMiddleware (which runs before this middleware) guarantees
        # that request.user is present.
        if request.user.is_authenticated:
            return self.get_response(request)

        # Paths that should remain accessible even when the gate is enabled
        allowed_paths = [
            '/admin/',
            '/health/',
            '/robots.txt',
            '/static/',
            '/media/',
            settings.LOGIN_URL,
        ]

        if any(request.path.startswith(path) for path in allowed_paths):
            return self.get_response(request)

        # Redirect anonymous users to the login page
        return redirect(settings.LOGIN_URL)
