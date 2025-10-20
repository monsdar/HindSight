from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from .views import health


def robots_txt(request):
    """Serve robots.txt to prevent web crawlers and scrapers."""
    content = """User-agent: *
Disallow: /

# This site is private and should not be indexed or scraped
# No AI training data collection allowed"""
    return HttpResponse(content, content_type='text/plain')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('hooptipp.predictions.urls', namespace='predictions')),
    path('health/', health, name='health'),
    path('robots.txt', robots_txt, name='robots_txt'),
]
