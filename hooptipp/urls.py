from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from .views import health, privacy_gate
from .auth_views import signup, profile


def robots_txt(request):
    """Serve robots.txt to prevent web crawlers and scrapers."""
    content = """User-agent: *
Disallow: /

# This site is private and should not be indexed or scraped
# No AI training data collection allowed"""
    return HttpResponse(content, content_type='text/plain')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health, name='health'),
    path('robots.txt', robots_txt, name='robots_txt'),
    
    # Authentication URLs (available in both modes, but functional only when ENABLE_USER_SELECTION=False)
    path('signup/', signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('profile/', profile, name='profile'),
    
    # Password reset flow
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(template_name='auth/password_reset.html'),
         name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='auth/password_reset_done.html'),
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name='auth/password_reset_confirm.html'),
         name='password_reset_confirm'),
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='auth/password_reset_complete.html'),
         name='password_reset_complete'),
    
    # Privacy gate (only used in USER_SELECTION mode)
    path('privacy-gate/', privacy_gate, name='privacy_gate'),
    
    # Main app URLs
    path('', include('hooptipp.predictions.urls', namespace='predictions')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
