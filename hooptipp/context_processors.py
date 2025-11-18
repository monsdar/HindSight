"""Context processors for HindSight application."""

from django.conf import settings


def page_customization(request):
    """
    Add page customization settings to the template context.
    
    Makes PAGE_TITLE and PAGE_SLOGAN available in all templates.
    """
    return {
        'PAGE_TITLE': settings.PAGE_TITLE,
        'PAGE_SLOGAN': settings.PAGE_SLOGAN,
    }

