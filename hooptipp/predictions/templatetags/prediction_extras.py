from datetime import timedelta

from django import template
from django.template.loader import render_to_string
from django.utils import timezone

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
    If both short and long templates exist, renders a collapsible wrapper.

    Usage:
        {% render_prediction_card event user_tip %}
    """
    # Find the appropriate renderer
    renderer = registry.get_renderer(event)

    # Get context from renderer
    card_context = renderer.get_event_context(event, user=context.get("active_user"))

    # Get users who have predicted this event
    event_tip_users = context.get("event_tip_users", {})
    users_who_predicted = event_tip_users.get(event.id, [])

    # Build base render context
    base_context = {
        "event": event,
        "user_tip": user_tip,
        "active_user": context.get("active_user"),
        "lock_summary": context.get("lock_summary"),
        "card_context": card_context,
        "palette": context.get("active_theme_palette"),
        "users_who_predicted": users_who_predicted,
    }

    # Check if both short and long templates exist
    short_template = renderer.get_event_template_short(event)
    long_template = renderer.get_event_template_long(event)

    if short_template and long_template:
        # Both templates exist - render collapsible wrapper
        short_html = render_to_string(short_template, base_context, request=context.get("request"))
        long_html = render_to_string(long_template, base_context, request=context.get("request"))
        
        wrapper_context = {
            **base_context,
            "short_template_html": short_html,
            "long_template_html": long_html,
            "has_toggle": True,
        }
        
        return render_to_string(
            "predictions/cards/collapsible_wrapper.html",
            wrapper_context,
            request=context.get("request")
        )
    elif short_template:
        # Only short template exists
        return render_to_string(short_template, base_context, request=context.get("request"))
    elif long_template:
        # Only long template exists
        return render_to_string(long_template, base_context, request=context.get("request"))
    else:
        # Fallback to original get_event_template method
        template_name = renderer.get_event_template(event)
        return render_to_string(template_name, base_context, request=context.get("request"))


@register.simple_tag(takes_context=True)
def render_result_card(context, outcome, user_tip=None, is_correct=None):
    """
    Render a resolved prediction result card using the appropriate template.

    Usage:
        {% render_result_card outcome user_tip is_correct %}
    """
    from ..models import UserTip, UserEventScore
    
    # Find the appropriate renderer
    renderer = registry.get_renderer(outcome.prediction_event)

    # Get template and context from renderer
    template_name = renderer.get_result_template(outcome)
    card_context = renderer.get_result_context(outcome, user=context.get("active_user"))

    # Get all users who predicted this event with their correctness and lock status
    users_who_predicted = []
    event = outcome.prediction_event
    
    # Fetch all tips for this event
    tips = UserTip.objects.filter(prediction_event=event).select_related('user')
    
    # Fetch all scores for this event to check lock bonuses
    scores = {
        score.user_id: score
        for score in UserEventScore.objects.filter(prediction_event=event)
    }
    
    # Fetch display names from UserPreferences
    from ..models import UserPreferences
    user_ids = [tip.user_id for tip in tips]
    display_name_map = {}
    if user_ids:
        for prefs in UserPreferences.objects.filter(user_id__in=user_ids):
            nickname = (prefs.nickname or '').strip()
            if nickname:
                display_name_map[prefs.user_id] = nickname
    
    # Helper function to check if tip matches outcome (same logic as scoring_service)
    def tip_matches_outcome(tip, outcome):
        if outcome.winning_option_id:
            if tip.prediction_option_id == outcome.winning_option_id:
                return True
            if tip.selected_option_id and outcome.winning_option and outcome.winning_option.option_id:
                return tip.selected_option_id == outcome.winning_option.option_id
            return False
        if outcome.winning_generic_option_id:
            return tip.selected_option_id == outcome.winning_generic_option_id
        return False
    
    # Build list of users with their prediction status
    for tip in tips:
        is_tip_correct = tip_matches_outcome(tip, outcome)
        score = scores.get(tip.user_id)
        was_locked = False
        lost_lock = False
        
        # Check if tip was locked (either via lock_status or is_lock_bonus in score)
        if tip.lock_status == UserTip.LockStatus.WAS_LOCKED:
            was_locked = True
        elif score and score.is_lock_bonus:
            was_locked = True
        
        # Check if user lost a lock due to incorrect prediction
        if not is_tip_correct and tip.lock_status == UserTip.LockStatus.FORFEITED:
            lost_lock = True
        
        # Apply display name
        user = tip.user
        user.display_name = display_name_map.get(user.id, user.username)
        
        users_who_predicted.append({
            'user': user,
            'is_correct': is_tip_correct,
            'was_locked': was_locked,
            'lost_lock': lost_lock,
        })
    
    # Check if outcome was resolved in the last 24 hours
    now = timezone.now()
    twenty_four_hours_ago = now - timedelta(hours=24)
    is_recent = outcome.resolved_at and outcome.resolved_at >= twenty_four_hours_ago
    
    # Build render context
    render_context = {
        "outcome": outcome,
        "event": outcome.prediction_event,
        "user_tip": user_tip,
        "is_correct": is_correct,
        "active_user": context.get("active_user"),
        "card_context": card_context,
        "user_score": card_context.get("user_score"),  # Extract user_score from card_context
        "palette": context.get("active_theme_palette"),
        "users_who_predicted": users_who_predicted,
        "is_recent": is_recent,
    }

    return render_to_string(template_name, render_context, request=context.get("request"))
