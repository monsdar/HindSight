from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from .views import health, privacy_gate
from .auth_views import (
    signup,
    profile,
    verify_email,
    verify_email_sent,
    verify_email_success,
    verify_email_failed,
    resend_verification,
    resend_verification_done,
    CustomLoginView,
    CustomPasswordResetView,
    CustomPasswordResetConfirmView,
)


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
    
    # Authentication URLs
    path('signup/', signup, name='signup'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('profile/', profile, name='profile'),
    
    # Email verification URLs
    path('verify-email-sent/', verify_email_sent, name='verify_email_sent'),
    path('verify-email/<str:uidb64>/<str:token>/', verify_email, name='verify_email'),
    path('verify-email-success/', verify_email_success, name='verify_email_success'),
    path('verify-email-failed/', verify_email_failed, name='verify_email_failed'),
    path('resend-verification/', resend_verification, name='resend_verification'),
    path('resend-verification/done/', resend_verification_done, name='resend_verification_done'),
    
    # Password reset flow
    path('password-reset/', 
         CustomPasswordResetView.as_view(),
         name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='auth/password_reset_done.html'),
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
         CustomPasswordResetConfirmView.as_view(),
         name='password_reset_confirm'),
    path('password-reset-confirm/<uidb64>/set-password/', 
         CustomPasswordResetConfirmView.as_view()),
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
