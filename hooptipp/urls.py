from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from .views import health, privacy_gate


def robots_txt(request):
    """Serve robots.txt to prevent web crawlers and scrapers."""
    content = """User-agent: *
Disallow: /

# This site is private and should not be indexed or scraped
# No AI training data collection allowed"""
    return HttpResponse(content, content_type='text/plain')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('privacy-gate/', privacy_gate, name='privacy_gate'),
    path('', include('hooptipp.predictions.urls', namespace='predictions')),
    path('health/', health, name='health'),
    path('robots.txt', robots_txt, name='robots_txt'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
