"""
Tests for the process_scores management command.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from django.contrib.auth import get_user_model

from hooptipp.predictions.models import (
    EventOutcome, Option, OptionCategory, PredictionEvent, 
    PredictionOption, TipType, UserTip, UserEventScore
)

User = get_user_model()


class ProcessScoresCommandTest(TestCase):
    """Test the process_scores management command."""

    def setUp(self):
        """Set up test data."""
        # Create test users
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        # Create option category and teams
        self.teams_cat = OptionCategory.objects.create(
            slug='nba-teams',
            name='NBA Teams',
            description='NBA team options'
        )
        
        self.home_team = Option.objects.create(
            category=self.teams_cat,
            slug='lakers',
            name='Los Angeles Lakers',
            short_name='LAL',
            external_id='14'
        )
        
        self.away_team = Option.objects.create(
            category=self.teams_cat,
            slug='warriors',
            name='Golden State Warriors',
            short_name='GSW',
            external_id='10'
        )
        
        # Create tip type
        self.tip_type = TipType.objects.create(
            name='Test Games',
            slug='test-games',
            description='Test tip type',
            deadline=timezone.now() + timedelta(hours=1)
        )
        
        # Create prediction event
        self.prediction_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='GSW @ LAL',
            description='Golden State Warriors at Los Angeles Lakers',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='test-source',
            source_event_id='12345',
            opens_at=timezone.now() - timedelta(hours=3),
            deadline=timezone.now() - timedelta(hours=2),
            reveal_at=timezone.now() - timedelta(hours=3),
            is_active=True,
            points=2
        )
        
        # Create prediction options
        self.home_option = PredictionOption.objects.create(
            event=self.prediction_event,
            option=self.home_team,
            label='Los Angeles Lakers',
            sort_order=1,
            is_active=True
        )
        
        self.away_option = PredictionOption.objects.create(
            event=self.prediction_event,
            option=self.away_team,
            label='Golden State Warriors',
            sort_order=2,
            is_active=True
        )
        
        # Create user tips
        self.user1_tip = UserTip.objects.create(
            user=self.user1,
            tip_type=self.tip_type,
            prediction_event=self.prediction_event,
            prediction_option=self.home_option,
            selected_option=self.home_team,
            prediction='Los Angeles Lakers will win',
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE
        )
        
        self.user2_tip = UserTip.objects.create(
            user=self.user2,
            tip_type=self.tip_type,
            prediction_event=self.prediction_event,
            prediction_option=self.away_option,
            selected_option=self.away_team,
            prediction='Golden State Warriors will win',
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE
        )
        
        # Create event outcome
        self.event_outcome = EventOutcome.objects.create(
            prediction_event=self.prediction_event,
            winning_option=self.home_option,
            winning_generic_option=self.home_team,
            resolved_at=timezone.now() - timedelta(hours=1)
        )

    def test_command_help(self):
        """Test that the command help is displayed correctly."""
        with self.assertRaises(SystemExit):
            call_command('process_scores', '--help')

    def test_dry_run_mode(self):
        """Test dry run mode shows what would be processed."""
        # Capture output
        from io import StringIO
        out = StringIO()
        
        call_command('process_scores', '--dry-run', stdout=out)
        
        output = out.getvalue()
        self.assertIn('DRY RUN - No changes will be made', output)
        self.assertIn('GSW @ LAL', output)
        self.assertIn('2 tips', output)
        self.assertIn('Would process 1 events with 2 total tips', output)
        
        # Verify no UserEventScore was created
        self.assertEqual(UserEventScore.objects.count(), 0)

    def test_process_scores_creates_scores(self):
        """Test that the command creates scores for correct predictions."""
        call_command('process_scores')
        
        # Verify UserEventScore was created for user1 (correct prediction)
        self.assertEqual(UserEventScore.objects.count(), 1)
        score = UserEventScore.objects.first()
        self.assertEqual(score.user, self.user1)
        self.assertEqual(score.prediction_event, self.prediction_event)
        self.assertEqual(score.points_awarded, 2)  # Base points
        self.assertEqual(score.base_points, 2)
        self.assertEqual(score.lock_multiplier, 1)
        self.assertFalse(score.is_lock_bonus)
        
        # Verify outcome was marked as scored
        self.event_outcome.refresh_from_db()
        self.assertIsNotNone(self.event_outcome.scored_at)

    def test_process_scores_with_locked_tip(self):
        """Test that locked tips get bonus points."""
        # Update user1 tip to be locked
        self.user1_tip.is_locked = True
        self.user1_tip.lock_status = UserTip.LockStatus.ACTIVE
        self.user1_tip.save()
        
        call_command('process_scores')
        
        # Verify UserEventScore was created with lock bonus
        self.assertEqual(UserEventScore.objects.count(), 1)
        score = UserEventScore.objects.first()
        self.assertEqual(score.user, self.user1)
        self.assertEqual(score.points_awarded, 4)  # 2 base points * 2 lock multiplier
        self.assertEqual(score.lock_multiplier, 2)
        self.assertTrue(score.is_lock_bonus)

    def test_process_scores_skips_incorrect_predictions(self):
        """Test that incorrect predictions don't get scores."""
        call_command('process_scores')
        
        # Only user1 should get a score (correct prediction)
        self.assertEqual(UserEventScore.objects.count(), 1)
        score = UserEventScore.objects.first()
        self.assertEqual(score.user, self.user1)
        
        # user2 should not have a score (incorrect prediction)
        self.assertFalse(UserEventScore.objects.filter(user=self.user2).exists())

    def test_process_scores_with_forfeited_lock(self):
        """Test that incorrect locked predictions forfeit the lock."""
        # Update user2 tip to be locked (incorrect prediction)
        self.user2_tip.is_locked = True
        self.user2_tip.lock_status = UserTip.LockStatus.ACTIVE
        self.user2_tip.save()
        
        call_command('process_scores')
        
        # user2 should not have a score (incorrect prediction)
        self.assertEqual(UserEventScore.objects.count(), 1)
        self.assertFalse(UserEventScore.objects.filter(user=self.user2).exists())
        
        # user2's lock should be forfeited
        self.user2_tip.refresh_from_db()
        self.assertEqual(self.user2_tip.lock_status, UserTip.LockStatus.FORFEITED)

    def test_hours_back_parameter(self):
        """Test the hours-back parameter."""
        # Create an older event that should be skipped
        old_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Old Game',
            description='Old game',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='test-source',
            source_event_id='99999',
            opens_at=timezone.now() - timedelta(hours=48),
            deadline=timezone.now() - timedelta(hours=47),
            reveal_at=timezone.now() - timedelta(hours=48),
            is_active=True,
            points=1
        )
        
        # Create outcome for old event
        old_outcome = EventOutcome.objects.create(
            prediction_event=old_event,
            winning_option=self.home_option,
            winning_generic_option=self.home_team,
            resolved_at=timezone.now() - timedelta(hours=48)  # 48 hours ago
        )
        
        # Run with default hours-back (24)
        call_command('process_scores')
        
        # Should only process the recent event
        self.assertEqual(UserEventScore.objects.count(), 1)
        
        # Clear scores
        UserEventScore.objects.all().delete()
        
        # Run with 48 hours back
        call_command('process_scores', '--hours-back', '48')
        
        # Should process both events
        self.assertEqual(UserEventScore.objects.count(), 1)  # Only one event has tips

    def test_force_parameter(self):
        """Test the force parameter."""
        # Create initial scores
        UserEventScore.objects.create(
            user=self.user1,
            prediction_event=self.prediction_event,
            base_points=1,
            lock_multiplier=1,
            points_awarded=1,
            is_lock_bonus=False
        )
        
        # Run without force
        call_command('process_scores')
        
        # Score should be updated, not created
        self.assertEqual(UserEventScore.objects.count(), 1)
        score = UserEventScore.objects.first()
        self.assertEqual(score.points_awarded, 2)  # Updated to correct value
        
        # Run with force
        call_command('process_scores', '--force')
        
        # Score should be updated again
        self.assertEqual(UserEventScore.objects.count(), 1)
        score = UserEventScore.objects.first()
        self.assertEqual(score.points_awarded, 2)

    def test_automation_disabled_environment_variable(self):
        """Test that automation can be disabled via environment variable."""
        with patch.dict(os.environ, {'AUTO_PROCESS_SCORES': 'false'}):
            call_command('process_scores')
            
            # Verify no UserEventScore was created
            self.assertEqual(UserEventScore.objects.count(), 0)

    def test_force_automation_override_environment_variable(self):
        """Test that --force-automation can override the environment variable."""
        with patch.dict(os.environ, {'AUTO_PROCESS_SCORES': 'false'}):
            call_command('process_scores', '--force-automation')
            
            # Verify UserEventScore was created despite disabled automation
            self.assertEqual(UserEventScore.objects.count(), 1)

    def test_environment_variable_hours_back(self):
        """Test that hours-back can be set via environment variable."""
        with patch.dict(os.environ, {'SCORE_PROCESSING_HOURS_BACK': '48'}):
            call_command('process_scores')
            
            # Verify UserEventScore was created
            self.assertEqual(UserEventScore.objects.count(), 1)

    def test_skip_events_without_outcomes(self):
        """Test that events without outcomes are skipped."""
        # Create event without outcome
        event_without_outcome = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='No Outcome Game',
            description='Game without outcome',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='test-source',
            source_event_id='99999',
            opens_at=timezone.now() - timedelta(hours=3),
            deadline=timezone.now() - timedelta(hours=2),
            reveal_at=timezone.now() - timedelta(hours=3),
            is_active=True,
            points=1
        )
        
        call_command('process_scores')
        
        # Should only process the event with outcome
        self.assertEqual(UserEventScore.objects.count(), 1)

    def test_skip_events_without_winning_option(self):
        """Test that events with outcomes but no winning option are skipped."""
        # Update the existing outcome to have no winning option
        self.event_outcome.winning_option = None
        self.event_outcome.winning_generic_option = None
        self.event_outcome.save()
        
        call_command('process_scores')
        
        # Should not create any scores
        self.assertEqual(UserEventScore.objects.count(), 0)

    def test_multiple_events_processing(self):
        """Test processing multiple events."""
        # Create another event
        event2 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Game 2',
            description='Second game',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='test-source',
            source_event_id='54321',
            opens_at=timezone.now() - timedelta(hours=3),
            deadline=timezone.now() - timedelta(hours=2),
            reveal_at=timezone.now() - timedelta(hours=3),
            is_active=True,
            points=3
        )
        
        # Create options for event2
        PredictionOption.objects.create(
            event=event2,
            option=self.home_team,
            label='Los Angeles Lakers',
            sort_order=1,
            is_active=True
        )
        
        # Create tip for event2
        UserTip.objects.create(
            user=self.user1,
            tip_type=self.tip_type,
            prediction_event=event2,
            prediction_option=self.home_option,
            selected_option=self.home_team,
            prediction='Los Angeles Lakers will win',
            is_locked=False,
            lock_status=UserTip.LockStatus.NONE
        )
        
        # Create outcome for event2
        EventOutcome.objects.create(
            prediction_event=event2,
            winning_option=self.home_option,
            winning_generic_option=self.home_team,
            resolved_at=timezone.now() - timedelta(hours=1)
        )
        
        call_command('process_scores')
        
        # Should create scores for both events
        self.assertEqual(UserEventScore.objects.count(), 2)
        
        # Check scores
        scores = UserEventScore.objects.all()
        event1_score = scores.get(prediction_event=self.prediction_event)
        event2_score = scores.get(prediction_event=event2)
        
        self.assertEqual(event1_score.points_awarded, 2)
        self.assertEqual(event2_score.points_awarded, 3)

    def test_error_handling(self):
        """Test that errors are handled gracefully."""
        # Mock the scoring service to raise an exception
        with patch('hooptipp.predictions.management.commands.process_scores.transaction.atomic') as mock_atomic:
            mock_atomic.side_effect = Exception('Database Error')
            
            # Should raise CommandError
            with self.assertRaises(CommandError):
                call_command('process_scores')

    def test_inactive_events_skipped(self):
        """Test that inactive events are skipped."""
        # Make the event inactive
        self.prediction_event.is_active = False
        self.prediction_event.save()
        
        call_command('process_scores')
        
        # Should not create any scores
        self.assertEqual(UserEventScore.objects.count(), 0)

    def test_outcome_already_scored(self):
        """Test that already scored outcomes are processed again."""
        # Mark outcome as already scored
        self.event_outcome.scored_at = timezone.now() - timedelta(minutes=30)
        self.event_outcome.save()
        
        call_command('process_scores')
        
        # Should still create/update scores
        self.assertEqual(UserEventScore.objects.count(), 1)
        
        # Outcome should have updated scored_at timestamp
        self.event_outcome.refresh_from_db()
        self.assertIsNotNone(self.event_outcome.scored_at)
