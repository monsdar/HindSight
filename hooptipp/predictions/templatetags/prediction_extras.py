from django import template
from django.template.loader import render_to_string

from ..card_renderers.registry import registry

register = template.Library()


@register.filter
def get_item(mapping, key):
    if not mapping:
        return None
    return mapping.get(key)


@register.simple_tag(takes_context=True)
def render_prediction_card(context, event, user_tip=None):
    """
    Render a prediction event card using the appropriate template.

    Finds the right card renderer via the registry and delegates rendering.

    Usage:
        {% render_prediction_card event user_tip %}
    """
    # Find the appropriate renderer
    renderer = registry.get_renderer(event)

    # Get template and context from renderer
    template_name = renderer.get_event_template(event)
    card_context = renderer.get_event_context(event, user=context.get("active_user"))

    # Get users who have predicted this event
    event_tip_users = context.get("event_tip_users", {})
    users_who_predicted = event_tip_users.get(event.id, [])

    # Build render context
    render_context = {
        "event": event,
        "user_tip": user_tip,
        "active_user": context.get("active_user"),
        "lock_summary": context.get("lock_summary"),
        "card_context": card_context,
        "palette": context.get("active_theme_palette"),
        "users_who_predicted": users_who_predicted,
    }

    return render_to_string(template_name, render_context, request=context.get("request"))


@register.simple_tag(takes_context=True)
def render_result_card(context, outcome, user_tip=None, is_correct=None):
    """
    Render a resolved prediction result card using the appropriate template.

    Usage:
        {% render_result_card outcome user_tip is_correct %}
    """
    # Find the appropriate renderer
    renderer = registry.get_renderer(outcome.prediction_event)

    # Get template and context from renderer
    template_name = renderer.get_result_template(outcome)
    card_context = renderer.get_result_context(outcome, user=context.get("active_user"))

    # Build render context
    render_context = {
        "outcome": outcome,
        "event": outcome.prediction_event,
        "user_tip": user_tip,
        "is_correct": is_correct,
        "active_user": context.get("active_user"),
        "card_context": card_context,
        "palette": context.get("active_theme_palette"),
    }

    return render_to_string(template_name, render_context, request=context.get("request"))
