"""Context processors for HindSight application."""

from django.conf import settings

from hooptipp.predictions.theme_palettes import DEFAULT_THEME_KEY, get_theme_palette


def page_customization(request):
    """
    Add page customization settings to the template context.
    
    Makes PAGE_TITLE, PAGE_SLOGAN, and active theme palette available in all templates.
    """
    # Get the active user's theme, or use default
    theme_key = DEFAULT_THEME_KEY
    
    # Try to get theme from active user if possible
    try:
        # Avoid circular import by importing here
        from hooptipp.user_context import get_active_user
        active_user = get_active_user(request)
        if active_user and hasattr(active_user, 'preferences'):
            theme_key = active_user.preferences.theme
    except (AttributeError, ImportError):
        # If request doesn't have user attribute (tests, etc.), use default
        pass
    
    active_theme_palette = get_theme_palette(theme_key)
    
    return {
        'PAGE_TITLE': settings.PAGE_TITLE,
        'PAGE_SLOGAN': settings.PAGE_SLOGAN,
        'active_theme_palette': active_theme_palette,
    }

