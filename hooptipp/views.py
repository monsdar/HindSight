"""Main views for HindSight application."""

from django.http import HttpResponse


def health(request):
    """Health check endpoint."""
    return HttpResponse("OK", content_type="text/plain")