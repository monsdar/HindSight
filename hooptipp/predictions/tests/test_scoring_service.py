from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from hooptipp.nba.models import NbaTeam
from hooptipp.predictions.models import (
    EventOutcome,
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
    UserEventScore,
    UserTip,
)
from hooptipp.predictions.scoring_service import LOCK_MULTIPLIER, score_event_outcome


class ScoreEventOutcomeTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        
        # Create option category for NBA teams
        self.teams_cat = OptionCategory.objects.create(
            slug='nba-teams',
            name='NBA Teams'
        )
        
        self.tip_type = TipType.objects.create(
            name="Weekly Games",
            slug="weekly-games",
            description="",
            category=TipType.TipCategory.GAME,
            default_points=1,
            deadline=timezone.now() + timedelta(days=1),
            is_active=True,
        )
        self.event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="BOS @ LAL",
            description="",
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            points=3,
            opens_at=timezone.now() - timedelta(hours=2),
            deadline=timezone.now() - timedelta(hours=1),
            reveal_at=timezone.now() - timedelta(hours=3),
            is_active=True,
        )
        
        # Create NbaTeam objects (still used for legacy data)
        self.lakers = NbaTeam.objects.create(name="Los Angeles Lakers", abbreviation="LAL")
        self.celtics = NbaTeam.objects.create(name="Boston Celtics", abbreviation="BOS")
        
        # Create generic Options
        self.lakers_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='lal',
            name='Los Angeles Lakers',
            short_name='LAL',
            metadata={'nba_team_id': self.lakers.id}
        )
        self.celtics_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='bos',
            name='Boston Celtics',
            short_name='BOS',
            metadata={'nba_team_id': self.celtics.id}
        )
        
        # Create PredictionOptions using generic Options
        self.lakers_option = PredictionOption.objects.create(
            event=self.event,
            label="Los Angeles Lakers",
            option=self.lakers_option_obj,
            sort_order=1,
        )
        self.celtics_option = PredictionOption.objects.create(
            event=self.event,
            label="Boston Celtics",
            option=self.celtics_option_obj,
            sort_order=2,
        )

    def test_scores_correct_tip_with_lock_multiplier(self) -> None:
        locked_user = self.user_model.objects.create_user("locked", "locked@example.com", "password")
        unlocked_user = self.user_model.objects.create_user("open", "open@example.com", "password")

        locked_tip = UserTip.objects.create(
            user=locked_user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        unlocked_tip = UserTip.objects.create(
            user=unlocked_user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.celtics_option,
            selected_option=self.celtics_option_obj,
            prediction="Boston Celtics",
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE,
        )

        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )

        result = score_event_outcome(outcome)

        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(result.skipped_tips, 1)
        self.assertEqual(UserEventScore.objects.count(), 1)
        awarded_score = UserEventScore.objects.get()
        self.assertEqual(awarded_score.user, locked_user)
        self.assertEqual(awarded_score.points_awarded, self.event.points * LOCK_MULTIPLIER)
        self.assertTrue(awarded_score.is_lock_bonus)
        locked_tip.refresh_from_db()
        self.assertTrue(locked_tip.is_locked)

    def test_idempotent_scoring_returns_existing_rows(self) -> None:
        user = self.user_model.objects.create_user("repeat", "repeat@example.com", "password")
        UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE,
        )
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )

        first_result = score_event_outcome(outcome)
        self.assertEqual(first_result.created_count, 1)

        second_result = score_event_outcome(outcome)
        self.assertEqual(second_result.created_count, 0)
        self.assertEqual(second_result.updated_count, 1)
        self.assertEqual(second_result.skipped_tips, 0)
        self.assertEqual(UserEventScore.objects.count(), 1)

    def test_force_rescore_recalculates_points(self) -> None:
        user = self.user_model.objects.create_user("force", "force@example.com", "password")
        tip = UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE,
        )
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )
        score_event_outcome(outcome)

        self.event.points = 10
        self.event.save(update_fields=["points"])
        tip.lock_status = UserTip.LockStatus.RETURNED
        tip.save(update_fields=["lock_status"])

        updated_outcome = EventOutcome.objects.get(pk=outcome.pk)
        result = score_event_outcome(updated_outcome, force=True)

        self.assertEqual(result.created_count, 1)
        awarded = UserEventScore.objects.get()
        self.assertEqual(awarded.points_awarded, 10 * LOCK_MULTIPLIER)
        self.assertTrue(awarded.is_lock_bonus)

    def test_scores_any_selection_team_event(self) -> None:
        any_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Winner",
            description="",
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.ANY,
            points=2,
            opens_at=timezone.now() - timedelta(hours=2),
            deadline=timezone.now() - timedelta(hours=1),
            reveal_at=timezone.now() - timedelta(hours=3),
            is_active=True,
        )
        option = PredictionOption.objects.create(
            event=any_event,
            label="Los Angeles Lakers",
            option=self.lakers_option_obj,
            sort_order=1,
        )
        user = self.user_model.objects.create_user("any", "any@example.com", "password")
        UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=any_event,
            prediction_option=None,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE,
        )
        outcome = EventOutcome.objects.create(
            prediction_event=any_event,
            winning_generic_option=self.lakers_option_obj,
        )

        result = score_event_outcome(outcome)

        self.assertEqual(result.created_count, 1)
        score = UserEventScore.objects.get(prediction_event=any_event)
        self.assertEqual(score.points_awarded, any_event.points)
        self.assertFalse(score.is_lock_bonus)
        self.assertEqual(result.skipped_tips, 0)
