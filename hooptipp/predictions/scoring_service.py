"""Utility functions for awarding prediction scores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from django.db import transaction
from django.utils import timezone

from .models import EventOutcome, PredictionEvent, UserEventScore, UserTip

LOCK_MULTIPLIER = 2
_LOCK_BONUS_STATUSES = {
    UserTip.LockStatus.ACTIVE,
    UserTip.LockStatus.RETURNED,
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
            .select_related('user', 'prediction_option', 'selected_team', 'selected_player')
        )

        for tip in tips:
            if not _tip_matches_outcome(tip, outcome):
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

        outcome.scored_at = timezone.now()
        outcome.score_error = ''
        outcome.save(update_fields=['scored_at', 'score_error'])

    return ScoreEventResult(event=event, outcome=outcome, awarded_scores=awarded, skipped_tips=skipped)


def _outcome_has_selection(outcome: EventOutcome) -> bool:
    return any((outcome.winning_option_id, outcome.winning_team_id, outcome.winning_player_id))


def _tip_matches_outcome(tip: UserTip, outcome: EventOutcome) -> bool:
    if outcome.winning_option_id:
        if tip.prediction_option_id == outcome.winning_option_id:
            return True
        if tip.selected_team_id and outcome.winning_option and outcome.winning_option.team_id:
            return tip.selected_team_id == outcome.winning_option.team_id
        if tip.selected_player_id and outcome.winning_option and outcome.winning_option.player_id:
            return tip.selected_player_id == outcome.winning_option.player_id
        return False

    if outcome.winning_team_id:
        selected_team_id = _selected_team_id_for_tip(tip)
        return selected_team_id == outcome.winning_team_id

    if outcome.winning_player_id:
        selected_player_id = _selected_player_id_for_tip(tip)
        return selected_player_id == outcome.winning_player_id

    return False


def _selected_team_id_for_tip(tip: UserTip) -> Optional[int]:
    if tip.selected_team_id:
        return tip.selected_team_id
    if tip.prediction_option and tip.prediction_option.team_id:
        return tip.prediction_option.team_id
    return None


def _selected_player_id_for_tip(tip: UserTip) -> Optional[int]:
    if tip.selected_player_id:
        return tip.selected_player_id
    if tip.prediction_option and tip.prediction_option.player_id:
        return tip.prediction_option.player_id
    return None


def _calculate_lock_multiplier(tip: UserTip) -> int:
    if tip.lock_status in _LOCK_BONUS_STATUSES:
        return LOCK_MULTIPLIER
    return 1
