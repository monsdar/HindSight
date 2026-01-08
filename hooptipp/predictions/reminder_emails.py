"""
Reminder email utilities for sending reminders about unpredicted events.

Provides functions for sending reminder emails to users about events with
upcoming deadlines.
"""

from typing import List, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import PredictionEvent


def send_reminder_email(user, events: List[PredictionEvent], request=None) -> None:
    """
    Send reminder email to user about unpredicted events.
    
    Args:
        user: User instance to send reminder email to
        events: List of PredictionEvent instances that need predictions
        request: Optional HttpRequest object for building absolute URLs
    """
    # Build predictions URL
    if request:
        protocol = 'https' if request.is_secure() else 'http'
        domain = request.get_host()
        predictions_url = f"{protocol}://{domain}{reverse('predictions:home')}"
    else:
        # Fallback if no request available (e.g., in management commands)
        host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'
        protocol = 'https' if not host.startswith(('localhost', '127.0.0.1', '0.0.0.0')) else 'http'
        predictions_url = f"{protocol}://{host}{reverse('predictions:home')}"
    
    # Build disable reminders URL
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    
    if request:
        protocol = 'https' if request.is_secure() else 'http'
        domain = request.get_host()
        disable_url = f"{protocol}://{domain}{reverse('predictions:disable_reminders', args=[uid, token])}"
    else:
        host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'
        protocol = 'https' if not host.startswith(('localhost', '127.0.0.1', '0.0.0.0')) else 'http'
        disable_url = f"{protocol}://{host}{reverse('predictions:disable_reminders', args=[uid, token])}"
    
    # Get site name from settings
    site_name = getattr(settings, 'PAGE_TITLE', 'HindSight')
    
    # Email subject
    subject = f'Erinnerung: Offene Tipps - {site_name}'
    
    # Render email templates
    context = {
        'user': user,
        'events': events,
        'predictions_url': predictions_url,
        'disable_url': disable_url,
        'site_name': site_name,
    }
    
    html_message = render_to_string('emails/reminder_email.html', context)
    plain_message = render_to_string('emails/reminder_email.txt', context)
    
    # Send email
    from_email = settings.DEFAULT_FROM_EMAIL
    send_mail(
        subject=subject,
        message=plain_message,
        from_email=from_email,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )

