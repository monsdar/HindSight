from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

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
from hooptipp.predictions.scoring_service import LOCK_MULTIPLIER, score_event_outcome, process_all_user_scores


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
        
        # Create generic Options
        self.lakers_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='lal',
            name='Los Angeles Lakers',
            short_name='LAL',
            external_id='1',
            metadata={'city': 'Los Angeles', 'conference': 'West', 'division': 'Pacific'}
        )
        self.celtics_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='bos',
            name='Boston Celtics',
            short_name='BOS',
            external_id='2',
            metadata={'city': 'Boston', 'conference': 'East', 'division': 'Atlantic'}
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
        # Lock should be returned to user after scoring (status goes to WAS_LOCKED to preserve bonus points)
        self.assertFalse(locked_tip.is_locked)
        self.assertEqual(locked_tip.lock_status, UserTip.LockStatus.WAS_LOCKED)
        self.assertIsNotNone(locked_tip.lock_released_at)

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

    def test_idempotent_scoring_with_locks_maintains_state(self) -> None:
        """Test that scoring with locks is idempotent and preserves bonus points on subsequent runs."""
        user = self.user_model.objects.create_user("lockidempotent", "lockidempotent@example.com", "password")
        tip = UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )

        # First scoring should release the lock and set status to WAS_LOCKED
        first_result = score_event_outcome(outcome)
        self.assertEqual(first_result.created_count, 1)
        self.assertTrue(first_result.awarded_scores[0].score.is_lock_bonus)
        self.assertEqual(first_result.awarded_scores[0].score.points_awarded, self.event.points * LOCK_MULTIPLIER)
        tip.refresh_from_db()
        self.assertFalse(tip.is_locked)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.WAS_LOCKED)
        first_lock_status = tip.lock_status
        first_released_at = tip.lock_released_at

        # Second scoring should be idempotent - bonus points should persist
        second_result = score_event_outcome(outcome, force=True)
        self.assertEqual(second_result.created_count, 1)
        self.assertEqual(second_result.updated_count, 0)
        tip.refresh_from_db()
        # Lock status should remain WAS_LOCKED (idempotent)
        self.assertEqual(tip.lock_status, first_lock_status)
        self.assertEqual(tip.lock_released_at, first_released_at)
        # Score should still have lock bonus because WAS_LOCKED status is counted
        self.assertTrue(second_result.awarded_scores[0].score.is_lock_bonus)
        self.assertEqual(second_result.awarded_scores[0].score.points_awarded, self.event.points * LOCK_MULTIPLIER)

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
        # Set lock status to ACTIVE to test that bonus points are awarded
        tip.is_locked = True
        tip.lock_status = UserTip.LockStatus.ACTIVE
        tip.save(update_fields=["is_locked", "lock_status"])

        updated_outcome = EventOutcome.objects.get(pk=outcome.pk)
        result = score_event_outcome(updated_outcome, force=True)

        self.assertEqual(result.created_count, 1)
        awarded = UserEventScore.objects.get()
        self.assertEqual(awarded.points_awarded, 10 * LOCK_MULTIPLIER)
        self.assertTrue(awarded.is_lock_bonus)

    def test_returned_status_does_not_give_bonus_points(self) -> None:
        """Test that RETURNED lock status does not award bonus points.
        
        RETURNED status should only be used when a forfeited lock is automatically
        returned after cooldown. It should not be confused with manually released locks
        (which use NONE status) and should not award bonus points.
        """
        user = self.user_model.objects.create_user("returned", "returned@example.com", "password")
        tip = UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=False,
            lock_status=UserTip.LockStatus.RETURNED,  # Simulating a lock that was forfeited and returned
        )
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )

        result = score_event_outcome(outcome)

        self.assertEqual(result.created_count, 1)
        awarded = UserEventScore.objects.get()
        # Should get base points only, no bonus (RETURNED status should not give bonus)
        self.assertEqual(awarded.points_awarded, self.event.points)
        self.assertFalse(awarded.is_lock_bonus)
        self.assertEqual(awarded.lock_multiplier, 1)

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


class ProcessAllUserScoresTests(TestCase):
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
        
        # Create two events
        self.event1 = PredictionEvent.objects.create(
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
        
        self.event2 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="GSW @ MIA",
            description="",
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            points=2,
            opens_at=timezone.now() - timedelta(hours=2),
            deadline=timezone.now() - timedelta(hours=1),
            reveal_at=timezone.now() - timedelta(hours=3),
            is_active=True,
        )
        
        # Create generic Options
        self.lakers_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='lal',
            name='Los Angeles Lakers',
            short_name='LAL',
            external_id='1',
        )
        self.celtics_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='bos',
            name='Boston Celtics',
            short_name='BOS',
            external_id='2',
        )
        self.warriors_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='gsw',
            name='Golden State Warriors',
            short_name='GSW',
            external_id='3',
        )
        self.heat_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='mia',
            name='Miami Heat',
            short_name='MIA',
            external_id='4',
        )
        
        # Create PredictionOptions
        self.lakers_option = PredictionOption.objects.create(
            event=self.event1,
            label="Los Angeles Lakers",
            option=self.lakers_option_obj,
            sort_order=1,
        )
        self.celtics_option = PredictionOption.objects.create(
            event=self.event1,
            label="Boston Celtics",
            option=self.celtics_option_obj,
            sort_order=2,
        )
        
        self.warriors_option = PredictionOption.objects.create(
            event=self.event2,
            label="Golden State Warriors",
            option=self.warriors_option_obj,
            sort_order=1,
        )
        self.heat_option = PredictionOption.objects.create(
            event=self.event2,
            label="Miami Heat",
            option=self.heat_option_obj,
            sort_order=2,
        )

    def test_process_all_scores_creates_scores_for_multiple_events(self) -> None:
        """Test that process_all_user_scores processes multiple events correctly."""
        user1 = self.user_model.objects.create_user("user1", "user1@example.com", "password")
        user2 = self.user_model.objects.create_user("user2", "user2@example.com", "password")
        
        # Create tips for event1
        UserTip.objects.create(
            user=user1,
            tip_type=self.tip_type,
            prediction_event=self.event1,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        UserTip.objects.create(
            user=user2,
            tip_type=self.tip_type,
            prediction_event=self.event1,
            prediction_option=self.celtics_option,
            selected_option=self.celtics_option_obj,
            prediction="Boston Celtics",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        
        # Create tips for event2
        UserTip.objects.create(
            user=user1,
            tip_type=self.tip_type,
            prediction_event=self.event2,
            prediction_option=self.warriors_option,
            selected_option=self.warriors_option_obj,
            prediction="Golden State Warriors",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        UserTip.objects.create(
            user=user2,
            tip_type=self.tip_type,
            prediction_event=self.event2,
            prediction_option=self.heat_option,
            selected_option=self.heat_option_obj,
            prediction="Miami Heat",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        
        # Create outcomes
        EventOutcome.objects.create(
            prediction_event=self.event1,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )
        EventOutcome.objects.create(
            prediction_event=self.event2,
            winning_option=self.warriors_option,
            winning_generic_option=self.warriors_option_obj,
        )
        
        # Process all scores
        result = process_all_user_scores()
        
        # Verify results
        self.assertEqual(result.total_events_processed, 2)
        self.assertEqual(result.total_scores_created, 2)  # user1 for both events
        self.assertEqual(result.total_scores_updated, 0)
        self.assertEqual(result.total_tips_skipped, 2)  # user2 for both events (wrong picks)
        self.assertEqual(result.total_locks_returned, 2)  # user1 had locks on both events
        self.assertEqual(result.total_locks_forfeited, 2)  # user2 had locks on both events (wrong picks)
        self.assertEqual(len(result.events_with_errors), 0)
        
        # Verify UserEventScore records
        scores = UserEventScore.objects.all()
        self.assertEqual(scores.count(), 2)
        
        # user1 event1: 3 points * 2 (lock multiplier) = 6 points
        user1_event1_score = scores.get(user=user1, prediction_event=self.event1)
        self.assertEqual(user1_event1_score.points_awarded, 6)
        self.assertTrue(user1_event1_score.is_lock_bonus)
        
        # user1 event2: 2 points * 2 (lock multiplier) = 4 points
        user1_event2_score = scores.get(user=user1, prediction_event=self.event2)
        self.assertEqual(user1_event2_score.points_awarded, 4)
        self.assertTrue(user1_event2_score.is_lock_bonus)

    def test_process_all_scores_with_force_deletes_existing_scores(self) -> None:
        """Test that force=True deletes existing scores before processing."""
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
        
        # Create a tip
        UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event1,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE,
        )
        
        # Create outcome
        EventOutcome.objects.create(
            prediction_event=self.event1,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )
        
        # Create an existing score
        existing_score = UserEventScore.objects.create(
            user=user,
            prediction_event=self.event1,
            base_points=1,
            lock_multiplier=1,
            points_awarded=1,
        )
        
        # Process with force=True
        result = process_all_user_scores(force=True)
        
        # Verify the old score was deleted and new one created
        self.assertEqual(result.total_scores_created, 1)
        self.assertEqual(result.total_scores_updated, 0)
        self.assertEqual(result.total_locks_returned, 0)  # No lock on this tip
        self.assertEqual(result.total_locks_forfeited, 0)  # No lock on this tip
        
        scores = UserEventScore.objects.all()
        self.assertEqual(scores.count(), 1)
        
        new_score = scores.get()
        self.assertNotEqual(new_score.id, existing_score.id)
        self.assertEqual(new_score.points_awarded, 3)  # event1.points = 3

    def test_process_all_scores_handles_events_without_outcomes(self) -> None:
        """Test that events without outcomes are skipped."""
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
        
        # Create a tip for an event without outcome
        UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event1,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE,
        )
        
        # Don't create an outcome for event1
        
        # Create outcome for event2
        EventOutcome.objects.create(
            prediction_event=self.event2,
            winning_option=self.warriors_option,
            winning_generic_option=self.warriors_option_obj,
        )
        
        # Process all scores
        result = process_all_user_scores()
        
        # Should only process event2
        self.assertEqual(result.total_events_processed, 1)
        self.assertEqual(result.total_scores_created, 0)  # No tips for event2
        self.assertEqual(result.total_scores_updated, 0)
        self.assertEqual(result.total_tips_skipped, 0)
        self.assertEqual(result.total_locks_returned, 0)  # No locks to return
        self.assertEqual(result.total_locks_forfeited, 0)  # No locks to forfeit
        self.assertEqual(UserEventScore.objects.count(), 0)

    def test_process_all_scores_handles_events_with_invalid_outcomes(self) -> None:
        """Test that events with invalid outcomes are handled gracefully."""
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
        
        # Create a tip
        UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event1,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE,
        )
        
        # Create outcome without winning option (invalid)
        EventOutcome.objects.create(
            prediction_event=self.event1,
            winning_option=None,
            winning_generic_option=None,
        )
        
        # Process all scores
        result = process_all_user_scores()
        
        # Should report error for event1
        self.assertEqual(result.total_events_processed, 0)
        self.assertEqual(result.total_scores_created, 0)
        self.assertEqual(result.total_scores_updated, 0)
        self.assertEqual(result.total_tips_skipped, 0)
        self.assertEqual(result.total_locks_returned, 0)
        self.assertEqual(result.total_locks_forfeited, 0)
        self.assertEqual(len(result.events_with_errors), 1)
        self.assertIn("No winning option specified", result.events_with_errors[0])
        self.assertEqual(UserEventScore.objects.count(), 0)

    def test_process_all_scores_updates_existing_scores(self) -> None:
        """Test that existing scores are updated when processing again."""
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
        
        # Create a tip
        UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event1,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE,
        )
        
        # Create outcome
        EventOutcome.objects.create(
            prediction_event=self.event1,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )
        
        # Process first time
        result1 = process_all_user_scores()
        self.assertEqual(result1.total_scores_created, 1)
        self.assertEqual(result1.total_scores_updated, 0)
        self.assertEqual(result1.total_locks_returned, 0)  # No lock on this tip
        self.assertEqual(result1.total_locks_forfeited, 0)  # No lock on this tip
        
        # Change event points and process again
        self.event1.points = 5
        self.event1.save()
        
        result2 = process_all_user_scores()
        self.assertEqual(result2.total_scores_created, 0)
        self.assertEqual(result2.total_scores_updated, 1)
        self.assertEqual(result2.total_locks_returned, 0)  # No lock on this tip
        self.assertEqual(result2.total_locks_forfeited, 0)  # No lock on this tip
        
        # Verify the score was updated
        score = UserEventScore.objects.get()
        self.assertEqual(score.points_awarded, 5)
        self.assertEqual(score.base_points, 5)

    def test_process_all_scores_returns_locks_to_users(self) -> None:
        """Test that locks are returned to users when processing scores."""
        user1 = self.user_model.objects.create_user("user1", "user1@example.com", "password")
        user2 = self.user_model.objects.create_user("user2", "user2@example.com", "password")
        
        # Create tips with locks
        tip1 = UserTip.objects.create(
            user=user1,
            tip_type=self.tip_type,
            prediction_event=self.event1,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        tip2 = UserTip.objects.create(
            user=user2,
            tip_type=self.tip_type,
            prediction_event=self.event1,
            prediction_option=self.celtics_option,
            selected_option=self.celtics_option_obj,
            prediction="Boston Celtics",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        
        # Create outcome (Lakers win)
        EventOutcome.objects.create(
            prediction_event=self.event1,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )
        
        # Process all scores
        result = process_all_user_scores()
        
        # Verify results
        self.assertEqual(result.total_events_processed, 1)
        self.assertEqual(result.total_scores_created, 1)  # Only user1 gets points
        self.assertEqual(result.total_scores_updated, 0)
        self.assertEqual(result.total_tips_skipped, 1)  # user2's tip was wrong
        self.assertEqual(result.total_locks_returned, 1)  # Only user1's lock is returned
        self.assertEqual(result.total_locks_forfeited, 1)  # user2's lock is forfeited
        self.assertEqual(len(result.events_with_errors), 0)
        
        # Verify lock status changes
        tip1.refresh_from_db()
        tip2.refresh_from_db()
        
        # user1's lock should be returned (correct prediction) - status goes to WAS_LOCKED to preserve bonus points
        self.assertFalse(tip1.is_locked)
        self.assertEqual(tip1.lock_status, UserTip.LockStatus.WAS_LOCKED)
        self.assertIsNotNone(tip1.lock_released_at)
        
        # user2's lock should be forfeited (wrong prediction)
        self.assertFalse(tip2.is_locked)
        self.assertEqual(tip2.lock_status, UserTip.LockStatus.FORFEITED)
        self.assertIsNotNone(tip2.lock_releases_at)
        self.assertIsNone(tip2.lock_released_at)

    def test_process_all_scores_forfeits_locks_for_incorrect_predictions(self) -> None:
        """Test that locks are forfeited for incorrect predictions with proper scheduling."""
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
        
        # Create a tip with lock
        tip = UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event1,
            prediction_option=self.celtics_option,  # Wrong choice
            selected_option=self.celtics_option_obj,
            prediction="Boston Celtics",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        
        # Create outcome (Lakers win)
        outcome = EventOutcome.objects.create(
            prediction_event=self.event1,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )
        
        # Process all scores
        result = process_all_user_scores()
        
        # Verify results
        self.assertEqual(result.total_events_processed, 1)
        self.assertEqual(result.total_scores_created, 0)  # No correct predictions
        self.assertEqual(result.total_scores_updated, 0)
        self.assertEqual(result.total_tips_skipped, 1)  # Wrong prediction
        self.assertEqual(result.total_locks_returned, 0)  # No locks returned
        self.assertEqual(result.total_locks_forfeited, 1)  # One lock forfeited
        self.assertEqual(len(result.events_with_errors), 0)
        
        # Verify lock status changes
        tip.refresh_from_db()
        
        # Lock should be forfeited and scheduled for return
        self.assertFalse(tip.is_locked)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.FORFEITED)
        self.assertIsNotNone(tip.lock_releases_at)
        self.assertIsNone(tip.lock_released_at)
        
        # Verify the release time is set to 30 days after resolution
        expected_release_time = outcome.resolved_at + timedelta(days=30)
        self.assertEqual(tip.lock_releases_at, expected_release_time)
        
        # Verify lock_forfeited_at is set to resolved_at
        self.assertEqual(tip.lock_forfeited_at, outcome.resolved_at)

    def test_process_all_user_scores_idempotent_with_locks(self) -> None:
        """Test that process_all_user_scores maintains bonus points on subsequent runs."""
        user = self.user_model.objects.create_user("processidempotent", "processidempotent@example.com", "password")
        
        # Create tip with active lock
        tip = UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event1,
            prediction_option=self.lakers_option,
            selected_option=self.lakers_option_obj,
            prediction="Los Angeles Lakers",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        
        # Create outcome
        EventOutcome.objects.create(
            prediction_event=self.event1,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )
        
        # First run - should create score with bonus points and set status to WAS_LOCKED
        result1 = process_all_user_scores()
        self.assertEqual(result1.total_events_processed, 1)
        self.assertEqual(result1.total_scores_created, 1)
        self.assertEqual(result1.total_locks_returned, 1)
        
        score1 = UserEventScore.objects.get()
        self.assertEqual(score1.points_awarded, self.event1.points * LOCK_MULTIPLIER)
        self.assertTrue(score1.is_lock_bonus)
        
        tip.refresh_from_db()
        self.assertEqual(tip.lock_status, UserTip.LockStatus.WAS_LOCKED)
        
        # Second run - should update score but preserve bonus points
        result2 = process_all_user_scores()
        self.assertEqual(result2.total_events_processed, 1)
        self.assertEqual(result2.total_scores_created, 0)
        self.assertEqual(result2.total_scores_updated, 1)
        self.assertEqual(result2.total_locks_returned, 0)  # Lock already returned, not ACTIVE anymore
        
        score2 = UserEventScore.objects.get()
        # Bonus points should be preserved (idempotent)
        self.assertEqual(score2.points_awarded, self.event1.points * LOCK_MULTIPLIER)
        self.assertTrue(score2.is_lock_bonus)
        self.assertEqual(score2.id, score1.id)  # Same score record updated
        
        tip.refresh_from_db()
        # Status should remain WAS_LOCKED (idempotent)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.WAS_LOCKED)


class ForfeitedMatchTests(TestCase):
    """Tests for handling forfeited matches (20-0 scores with is_forfeit flag)."""
    
    def setUp(self) -> None:
        self.user_model = get_user_model()
        
        # Create option category for teams
        self.teams_cat = OptionCategory.objects.create(
            slug='dbb-teams',
            name='DBB Teams'
        )
        
        self.tip_type = TipType.objects.create(
            name="DBB Matches",
            slug="dbb-matches",
            description="",
            category=TipType.TipCategory.GAME,
            default_points=1,
            deadline=timezone.now() + timedelta(days=1),
            is_active=True,
        )
        self.event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Team A vs Team B",
            description="",
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            points=3,
            opens_at=timezone.now() - timedelta(hours=2),
            deadline=timezone.now() - timedelta(hours=1),
            reveal_at=timezone.now() - timedelta(hours=3),
            is_active=True,
        )
        
        # Create generic Options
        self.team_a_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='team-a',
            name='Team A',
            short_name='A',
        )
        self.team_b_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='team-b',
            name='Team B',
            short_name='B',
        )
        
        # Create PredictionOptions
        self.team_a_option = PredictionOption.objects.create(
            event=self.event,
            label="Team A",
            option=self.team_a_option_obj,
            sort_order=1,
        )
        self.team_b_option = PredictionOption.objects.create(
            event=self.event,
            label="Team B",
            option=self.team_b_option_obj,
            sort_order=2,
        )
    
    def test_score_event_outcome_handles_forfeited_match(self) -> None:
        """Test that forfeited matches don't award points but return locks."""
        user1 = self.user_model.objects.create_user("user1", "user1@example.com", "password")
        user2 = self.user_model.objects.create_user("user2", "user2@example.com", "password")
        
        # Create tips with locks
        tip1 = UserTip.objects.create(
            user=user1,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.team_a_option,
            selected_option=self.team_a_option_obj,
            prediction="Team A",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        tip2 = UserTip.objects.create(
            user=user2,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.team_b_option,
            selected_option=self.team_b_option_obj,
            prediction="Team B",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        
        # Create outcome for forfeited match
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.team_a_option,
            winning_generic_option=self.team_a_option_obj,
            metadata={
                'home_score': 20,
                'away_score': 0,
                'is_forfeit': True  # Match was forfeited
            }
        )
        
        result = score_event_outcome(outcome)
        
        # No scores should be created (forfeited match)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(result.skipped_tips, 0)
        self.assertEqual(UserEventScore.objects.count(), 0)
        
        # Both locks should be returned (not forfeited)
        tip1.refresh_from_db()
        tip2.refresh_from_db()
        
        self.assertFalse(tip1.is_locked)
        self.assertEqual(tip1.lock_status, UserTip.LockStatus.NONE)
        self.assertIsNotNone(tip1.lock_released_at)
        
        self.assertFalse(tip2.is_locked)
        self.assertEqual(tip2.lock_status, UserTip.LockStatus.NONE)
        self.assertIsNotNone(tip2.lock_released_at)
    
    def test_process_all_scores_handles_forfeited_matches(self) -> None:
        """Test that process_all_user_scores correctly handles forfeited matches."""
        user1 = self.user_model.objects.create_user("user1", "user1@example.com", "password")
        user2 = self.user_model.objects.create_user("user2", "user2@example.com", "password")
        
        # Create tips with locks
        tip1 = UserTip.objects.create(
            user=user1,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.team_a_option,
            selected_option=self.team_a_option_obj,
            prediction="Team A",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        tip2 = UserTip.objects.create(
            user=user2,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.team_b_option,
            selected_option=self.team_b_option_obj,
            prediction="Team B",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        
        # Create outcome for forfeited match
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.team_a_option,
            winning_generic_option=self.team_a_option_obj,
            metadata={
                'home_score': 20,
                'away_score': 0,
                'is_forfeit': True  # Match was forfeited
            }
        )
        
        result = process_all_user_scores()
        
        # Event should be processed but no scores created
        self.assertEqual(result.total_events_processed, 1)
        self.assertEqual(result.total_scores_created, 0)
        self.assertEqual(result.total_scores_updated, 0)
        self.assertEqual(result.total_tips_skipped, 2)  # Both tips skipped
        self.assertEqual(result.total_locks_returned, 2)  # Both locks returned
        self.assertEqual(result.total_locks_forfeited, 0)  # No locks forfeited
        self.assertEqual(len(result.events_with_errors), 0)
        
        # Outcome should be marked as scored (processed)
        outcome.refresh_from_db()
        self.assertIsNotNone(outcome.scored_at)
        self.assertEqual(outcome.score_error, 'Forfeited match - no scoring')
        
        # Both locks should be returned
        tip1.refresh_from_db()
        tip2.refresh_from_db()
        
        self.assertFalse(tip1.is_locked)
        self.assertEqual(tip1.lock_status, UserTip.LockStatus.NONE)
        
        self.assertFalse(tip2.is_locked)
        self.assertEqual(tip2.lock_status, UserTip.LockStatus.NONE)
    
    def test_forfeited_match_does_not_award_points_to_correct_prediction(self) -> None:
        """Test that even correct predictions don't get points for forfeited matches."""
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
        
        # Create tip predicting Team A (which would be the "winner" in forfeit)
        tip = UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.team_a_option,
            selected_option=self.team_a_option_obj,
            prediction="Team A",
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE,
        )
        
        # Create outcome for forfeited match (Team A "wins" 20-0)
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.team_a_option,
            winning_generic_option=self.team_a_option_obj,
            metadata={
                'home_score': 20,
                'away_score': 0,
                'is_forfeit': True  # Match was forfeited
            }
        )
        
        result = score_event_outcome(outcome)
        
        # No scores should be created (forfeited match doesn't count)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(UserEventScore.objects.count(), 0)
    
    def test_forfeited_match_does_not_count_as_incorrect(self) -> None:
        """Test that incorrect predictions on forfeited matches don't forfeit locks."""
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
        
        # Create tip predicting Team B (which would be the "loser" in forfeit)
        tip = UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.team_b_option,
            selected_option=self.team_b_option_obj,
            prediction="Team B",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        
        # Create outcome for forfeited match (Team A "wins" 20-0)
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.team_a_option,
            winning_generic_option=self.team_a_option_obj,
            metadata={
                'home_score': 20,
                'away_score': 0,
                'is_forfeit': True  # Match was forfeited
            }
        )
        
        result = score_event_outcome(outcome)
        
        # Lock should be returned, not forfeited
        tip.refresh_from_db()
        self.assertFalse(tip.is_locked)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.NONE)
        self.assertIsNotNone(tip.lock_released_at)
        self.assertIsNone(tip.lock_releases_at)  # No scheduled forfeit return
