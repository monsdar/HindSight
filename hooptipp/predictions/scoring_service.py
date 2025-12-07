"""Utility functions for awarding prediction scores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from django.db import transaction
from django.utils import timezone

from .models import EventOutcome, PredictionEvent, UserEventScore, UserTip
from .lock_service import LockService

LOCK_MULTIPLIER = 2
_LOCK_BONUS_STATUSES = {
    UserTip.LockStatus.ACTIVE,
    UserTip.LockStatus.WAS_LOCKED,
}


@dataclass(frozen=True)
class AwardedScore:
    """Snapshot of a single user's scoring result."""

    score: UserEventScore
    created: bool


@dataclass(frozen=True)
class ScoreEventResult:
    """Summary returned when an event outcome is scored."""

    event: PredictionEvent
    outcome: EventOutcome
    awarded_scores: List[AwardedScore]
    skipped_tips: int

    @property
    def total_awarded_points(self) -> int:
        return sum(entry.score.points_awarded for entry in self.awarded_scores)

    @property
    def created_count(self) -> int:
        return sum(1 for entry in self.awarded_scores if entry.created)

    @property
    def updated_count(self) -> int:
        return len(self.awarded_scores) - self.created_count


def score_event_outcome(outcome: EventOutcome, *, force: bool = False) -> ScoreEventResult:
    """Award scores for all tips linked to ``outcome``.

    When ``force`` is ``True`` any existing :class:`~UserEventScore` rows linked to
    the outcome's prediction event are removed prior to recalculating results.
    This is useful when the winning selection changes and previous points must be
    revoked.
    """

    event = outcome.prediction_event
    if event is None:
        raise ValueError("EventOutcome must be associated with a PredictionEvent before scoring.")

    # Check if this is a forfeited match - if so, don't score it
    if _is_forfeited_match(outcome):
        # Return all locks for forfeited matches without scoring
        locks_returned = _return_locks_for_forfeited_match(outcome)
        # Return empty result since no scoring occurred
        return ScoreEventResult(event=event, outcome=outcome, awarded_scores=[], skipped_tips=0)

    if not _outcome_has_selection(outcome):
        raise ValueError("EventOutcome must specify a winning option, team, or player before scoring.")

    awarded: List[AwardedScore] = []
    skipped = 0

    with transaction.atomic():
        if force:
            UserEventScore.objects.filter(prediction_event=event).delete()
        elif outcome.scored_at:
            existing_scores = list(UserEventScore.objects.filter(prediction_event=event))
            if existing_scores:
                return ScoreEventResult(
                    event=event,
                    outcome=outcome,
                    awarded_scores=[
                        AwardedScore(score=score, created=False) for score in existing_scores
                    ],
                    skipped_tips=0,
                )

        tips = list(
            UserTip.objects.filter(prediction_event=event)
            .select_related('user', 'prediction_option', 'selected_option')
        )

        for tip in tips:
            if not _tip_matches_outcome(tip, outcome):
                # Handle incorrect predictions with locks - forfeit them
                if tip.lock_status == UserTip.LockStatus.ACTIVE:
                    lock_service = LockService(tip.user)
                    lock_service.schedule_forfeit(tip, resolved_at=outcome.resolved_at)
                skipped += 1
                continue

            base_points = event.points
            multiplier = _calculate_lock_multiplier(tip)
            total_points = base_points * multiplier
            defaults = {
                'base_points': base_points,
                'lock_multiplier': multiplier,
                'points_awarded': total_points,
                'is_lock_bonus': multiplier > 1,
            }

            score, created = UserEventScore.objects.update_or_create(
                user=tip.user,
                prediction_event=event,
                defaults=defaults,
            )
            awarded.append(AwardedScore(score=score, created=created))
            
            # Award hotness for correct prediction
            from .hotness_service import award_hotness_for_correct_prediction
            from .models import Season
            active_season = Season.get_active_season()
            award_hotness_for_correct_prediction(
                user=tip.user,
                was_locked=multiplier > 1,
                season=active_season
            )
            
            # Return lock to user if they had an active lock
            # Use WAS_LOCKED status to preserve bonus points for idempotency
            if tip.lock_status == UserTip.LockStatus.ACTIVE:
                lock_service = LockService(tip.user)
                lock_service.release_lock_after_scoring(tip)

        outcome.scored_at = timezone.now()
        outcome.score_error = ''
        outcome.save(update_fields=['scored_at', 'score_error'])

    return ScoreEventResult(event=event, outcome=outcome, awarded_scores=awarded, skipped_tips=skipped)


def _outcome_has_selection(outcome: EventOutcome) -> bool:
    return any((outcome.winning_option_id, outcome.winning_generic_option_id))


def _tip_matches_outcome(tip: UserTip, outcome: EventOutcome) -> bool:
    # Check if tip matches via PredictionOption
    if outcome.winning_option_id:
        if tip.prediction_option_id == outcome.winning_option_id:
            return True
        # Check if the user's selected option matches the winning option's option
        if tip.selected_option_id and outcome.winning_option and outcome.winning_option.option_id:
            return tip.selected_option_id == outcome.winning_option.option_id
        return False

    # Check if tip matches via generic Option
    if outcome.winning_generic_option_id:
        return tip.selected_option_id == outcome.winning_generic_option_id

    return False


def _calculate_lock_multiplier(tip: UserTip) -> int:
    if tip.lock_status in _LOCK_BONUS_STATUSES:
        return LOCK_MULTIPLIER
    return 1


def _is_forfeited_match(outcome: EventOutcome) -> bool:
    """Check if an outcome represents a forfeited match."""
    metadata = outcome.metadata or {}
    return metadata.get('is_forfeit', False)


def _return_locks_for_forfeited_match(outcome: EventOutcome) -> int:
    """Return all locks for a forfeited match without scoring.
    
    Returns:
        Number of locks returned
    """
    event = outcome.prediction_event
    tips_with_locks = UserTip.objects.filter(
        prediction_event=event,
        lock_status=UserTip.LockStatus.ACTIVE
    ).select_related('user')
    
    count = 0
    for tip in tips_with_locks:
        lock_service = LockService(tip.user)
        if lock_service.return_lock_for_forfeited_event(tip):
            count += 1
    
    return count


@dataclass(frozen=True)
class ProcessAllScoresResult:
    """Summary returned when processing all user scores."""
    
    total_events_processed: int
    total_scores_created: int
    total_scores_updated: int
    total_tips_skipped: int
    total_locks_returned: int
    total_locks_forfeited: int
    events_with_errors: List[str]


def process_all_user_scores(*, force: bool = False) -> ProcessAllScoresResult:
    """Process scores for all user tips that have corresponding event outcomes.
    
    This function goes through all UserTips and creates/updates UserEventScore
    records based on existing EventOutcomes.
    
    Args:
        force: If True, existing UserEventScore records are deleted before processing
        
    Returns:
        ProcessAllScoresResult with summary statistics
    """
    from django.db.models import Q
    
    total_events_processed = 0
    total_scores_created = 0
    total_scores_updated = 0
    total_tips_skipped = 0
    total_locks_returned = 0
    total_locks_forfeited = 0
    events_with_errors = []
    
    # Get all events that have outcomes
    events_with_outcomes = PredictionEvent.objects.filter(
        outcome__isnull=False
    ).select_related('outcome').prefetch_related('tips__user', 'tips__prediction_option', 'tips__selected_option')
    
    with transaction.atomic():
        if force:
            # Delete all existing scores if force is True
            UserEventScore.objects.all().delete()
        
        for event in events_with_outcomes:
            try:
                outcome = event.outcome
                
                # Check if this is a forfeited match - if so, return locks but don't score
                if _is_forfeited_match(outcome):
                    # Count locks before returning them
                    locks_count = event.tips.filter(lock_status=UserTip.LockStatus.ACTIVE).count()
                    # Return locks
                    locks_returned_count = _return_locks_for_forfeited_match(outcome)
                    total_locks_returned += locks_returned_count
                    # Count all tips as skipped since no scoring occurred
                    total_tips_skipped += event.tips.count()
                    total_events_processed += 1
                    
                    # Mark outcome as "scored" (processed) to avoid re-processing
                    if not outcome.scored_at:
                        outcome.scored_at = timezone.now()
                        outcome.score_error = 'Forfeited match - no scoring'
                        outcome.save(update_fields=['scored_at', 'score_error'])
                    continue
                
                if not _outcome_has_selection(outcome):
                    events_with_errors.append(f"{event.name}: No winning option specified")
                    continue
                
                total_events_processed += 1
                
                # Get all tips for this event
                tips = list(event.tips.all())
                
                for tip in tips:
                    if not _tip_matches_outcome(tip, outcome):
                        # Handle incorrect predictions with locks - forfeit them
                        if tip.lock_status == UserTip.LockStatus.ACTIVE:
                            lock_service = LockService(tip.user)
                            lock_service.schedule_forfeit(tip, resolved_at=outcome.resolved_at)
                            total_locks_forfeited += 1
                        total_tips_skipped += 1
                        continue
                    
                    base_points = event.points
                    multiplier = _calculate_lock_multiplier(tip)
                    total_points = base_points * multiplier
                    defaults = {
                        'base_points': base_points,
                        'lock_multiplier': multiplier,
                        'points_awarded': total_points,
                        'is_lock_bonus': multiplier > 1,
                    }
                    
                    score, created = UserEventScore.objects.update_or_create(
                        user=tip.user,
                        prediction_event=event,
                        defaults=defaults,
                    )
                    
                    if created:
                        total_scores_created += 1
                        # Award hotness for correct prediction (only when score is first created)
                        from .hotness_service import award_hotness_for_correct_prediction
                        from .models import Season
                        active_season = Season.get_active_season()
                        award_hotness_for_correct_prediction(
                            user=tip.user,
                            was_locked=multiplier > 1,
                            season=active_season
                        )
                    else:
                        total_scores_updated += 1
                    
                    # Return lock to user if they had an active lock
                    # Use WAS_LOCKED status to preserve bonus points for idempotency
                    if tip.lock_status == UserTip.LockStatus.ACTIVE:
                        lock_service = LockService(tip.user)
                        if lock_service.release_lock_after_scoring(tip):
                            total_locks_returned += 1
                
                # Mark the outcome as scored if it wasn't already
                if not outcome.scored_at:
                    outcome.scored_at = timezone.now()
                    outcome.score_error = ''
                    outcome.save(update_fields=['scored_at', 'score_error'])
                    
            except Exception as e:
                events_with_errors.append(f"{event.name}: {str(e)}")
                continue
    
    return ProcessAllScoresResult(
        total_events_processed=total_events_processed,
        total_scores_created=total_scores_created,
        total_scores_updated=total_scores_updated,
        total_tips_skipped=total_tips_skipped,
        total_locks_returned=total_locks_returned,
        total_locks_forfeited=total_locks_forfeited,
        events_with_errors=events_with_errors,
    )
