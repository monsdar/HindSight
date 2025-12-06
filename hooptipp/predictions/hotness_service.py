"""Service for managing user hotness scores."""

from __future__ import annotations
from datetime import date
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import UserHotness, HotnessKudos, Season, UserTip, UserEventScore, EventOutcome

User = get_user_model()

HOTNESS_CORRECT_PREDICTION = 10
HOTNESS_LOCK_WIN = 20
HOTNESS_STREAK_BONUS = 50
HOTNESS_KUDOS = 2
STREAK_LENGTH = 3


def get_or_create_hotness(user: User, season: Season | None = None) -> UserHotness:
    """Get or create hotness record for user in current season."""
    hotness, created = UserHotness.objects.get_or_create(
        user=user,
        season=season,
        defaults={'score': 0.0}
    )
    hotness.decay()
    return hotness


def give_kudos(from_user: User, to_user: User) -> dict:
    """
    Give kudos from one user to another.
    Returns dict with success status and message.
    Admin users can give unlimited kudos (for testing purposes).
    """
    if from_user == to_user:
        return {'success': False, 'message': 'Cannot give kudos to yourself'}
    
    today = timezone.now().date()
    active_season = Season.get_active_season()
    
    # Check if already gave kudos today (skip for admin users)
    if not from_user.is_staff:
        existing = HotnessKudos.objects.filter(
            from_user=from_user,
            to_user=to_user,
            created_at__date=today
        ).exists()
        
        if existing:
            return {'success': False, 'message': 'Already gave kudos to this user today'}
    
    with transaction.atomic():
        # Create kudos record
        HotnessKudos.objects.create(
            from_user=from_user,
            to_user=to_user,
            season=active_season
        )
        
        # Award hotness
        hotness = get_or_create_hotness(to_user, active_season)
        hotness.score += HOTNESS_KUDOS
        hotness.save(update_fields=['score'])
    
    return {
        'success': True,
        'new_score': hotness.score,
        'new_level': hotness.get_level()
    }


def award_hotness_for_correct_prediction(
    user: User,
    was_locked: bool = False,
    season: Season | None = None
) -> None:
    """Award hotness when user gets prediction correct."""
    hotness = get_or_create_hotness(user, season)
    
    # Base hotness for correct prediction
    hotness.score += HOTNESS_CORRECT_PREDICTION
    
    # Bonus for locked prediction
    if was_locked:
        hotness.score += HOTNESS_LOCK_WIN
    
    # Check for streak bonus
    # Get the most recent STREAK_LENGTH resolved events for which the user made a tip
    # Order by resolved_at to get chronological order of resolved predictions
    recent_resolved_events = list(
        EventOutcome.objects.filter(
            prediction_event__tips__user=user
        ).select_related('prediction_event').distinct().order_by('-resolved_at')[:STREAK_LENGTH]
    )
    
    # Check if we have at least STREAK_LENGTH resolved events
    if len(recent_resolved_events) >= STREAK_LENGTH:
        # Check if all of them have a UserEventScore (meaning all were correct)
        event_ids = [outcome.prediction_event_id for outcome in recent_resolved_events]
        correct_count = UserEventScore.objects.filter(
            user=user,
            prediction_event_id__in=event_ids
        ).count()
        
        # Only award streak bonus if all STREAK_LENGTH most recent resolved predictions were correct
        if correct_count >= STREAK_LENGTH:
            hotness.score += HOTNESS_STREAK_BONUS
    
    hotness.save(update_fields=['score'])


def get_user_kudos_given_today(user: User, target_users: list[User]) -> dict[int, bool]:
    """
    Get dict of user_id -> bool indicating if current user gave kudos today.
    """
    today = timezone.now().date()
    target_ids = [u.id for u in target_users]
    
    kudos = HotnessKudos.objects.filter(
        from_user=user,
        to_user_id__in=target_ids,
        created_at__date=today
    ).values_list('to_user_id', flat=True)
    
    return {user_id: user_id in kudos for user_id in target_ids}


def get_kudos_count_today(user: User) -> int:
    """Get count of kudos received by user today."""
    today = timezone.now().date()
    return HotnessKudos.objects.filter(
        to_user=user,
        created_at__date=today
    ).count()

