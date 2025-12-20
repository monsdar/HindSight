"""Tests for update_dbb_matches management command."""

from io import StringIO
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from hooptipp.dbb.models import TrackedLeague, TrackedTeam
from hooptipp.predictions.models import PredictionEvent, UserTip, TipType, OptionCategory, Option
from django.contrib.auth import get_user_model

User = get_user_model()


class UpdateDbbMatchesCommandTest(TestCase):
    """Tests for update_dbb_matches command."""

    def setUp(self):
        """Set up test data."""
        self.league = TrackedLeague.objects.create(
            verband_name='Test Verband',
            verband_id='v1',
            league_name='Test League',
            league_id='l1',
            club_search_term='Test Club',
            is_active=True
        )
        
        self.team = TrackedTeam.objects.create(
            tracked_league=self.league,
            team_name='BG Test Team',
            team_id='t1',
            is_active=True
        )

    @patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client')
    def test_command_without_api_token(self, mock_build_client):
        """Test command fails gracefully without API token."""
        mock_build_client.return_value = None
        
        out = StringIO()
        call_command('update_dbb_matches', stdout=out)
        
        output = out.getvalue()
        self.assertIn('SLAPI is not configured', output)

    @patch('hooptipp.dbb.management.commands.update_dbb_matches.DbbEventSource')
    @patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client')
    def test_command_with_dry_run(self, mock_build_client, mock_event_source_class):
        """Test command with dry-run flag."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        out = StringIO()
        call_command('update_dbb_matches', '--dry-run', stdout=out)
        
        output = out.getvalue()
        self.assertIn('DRY RUN MODE', output)

    @patch('hooptipp.dbb.management.commands.update_dbb_matches.DbbEventSource')
    @patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client')
    def test_command_syncs_matches(self, mock_build_client, mock_event_source_class):
        """Test command syncs matches successfully."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Mock event source
        mock_event_source = MagicMock()
        mock_event_source_class.return_value = mock_event_source
        
        # Mock sync results
        from hooptipp.predictions.event_sources.base import EventSourceResult
        options_result = EventSourceResult()
        options_result.options_created = 2
        events_result = EventSourceResult()
        events_result.events_created = 5
        
        mock_event_source.sync_options.return_value = options_result
        mock_event_source.sync_events.return_value = events_result
        
        out = StringIO()
        call_command('update_dbb_matches', stdout=out)
        
        output = out.getvalue()
        self.assertIn('Match update completed', output)
        
        # Verify event source methods were called
        mock_event_source.sync_options.assert_called_once()
        mock_event_source.sync_events.assert_called_once()

    @patch('hooptipp.dbb.management.commands.update_dbb_matches.DbbEventSource')
    @patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client')
    def test_command_with_specific_league(self, mock_build_client, mock_event_source_class):
        """Test command with specific league ID."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        mock_event_source = MagicMock()
        mock_event_source_class.return_value = mock_event_source
        
        from hooptipp.predictions.event_sources.base import EventSourceResult
        mock_event_source.sync_options.return_value = EventSourceResult()
        mock_event_source.sync_events.return_value = EventSourceResult()
        
        out = StringIO()
        call_command('update_dbb_matches', '--league-id', 'l1', stdout=out)
        
        output = out.getvalue()
        self.assertIn('Match update completed', output)

    def test_command_with_no_tracked_leagues(self):
        """Test command when no tracked leagues exist."""
        # Delete the league we created in setUp
        self.league.delete()
        
        out = StringIO()
        
        # Mock the client so it doesn't fail on API token check
        with patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client') as mock_build:
            mock_build.return_value = MagicMock()
            call_command('update_dbb_matches', stdout=out)
        
        output = out.getvalue()
        self.assertIn('No active tracked leagues', output)

    @patch('hooptipp.dbb.management.commands.update_dbb_matches.DbbEventSource')
    @patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client')
    def test_returns_locks_for_rescheduled_matches(self, mock_build_client, mock_event_source_class):
        """Test that locks are returned for matches that were rescheduled after lock was committed."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        mock_event_source = MagicMock()
        mock_event_source_class.return_value = mock_event_source
        
        from hooptipp.predictions.event_sources.base import EventSourceResult, RescheduledEvent
        mock_event_source.sync_options.return_value = EventSourceResult()
        mock_event_source.is_configured.return_value = True
        
        # Create a user
        user = User.objects.create_user(username='testuser', email='test@example.com', password='testpass')
        
        # Create tip type and category
        tip_type = TipType.objects.create(
            slug='dbb-matches',
            name='DBB Matches',
            category=TipType.TipCategory.GAME,
            is_active=True,
            default_points=1,
            deadline=timezone.now() + timedelta(days=30)
        )
        category = OptionCategory.objects.create(
            slug='dbb-teams',
            name='DBB Teams',
            is_active=True
        )
        
        # Simulate a match that was rescheduled:
        # - Old deadline was 2 days from now (close)
        # - Match was rescheduled to 10 days in the future (far)
        now = timezone.now()
        old_deadline = now + timedelta(days=2)  # Original deadline was close
        new_deadline = now + timedelta(days=10)  # Rescheduled to 10 days from now
        
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name='Team A vs Team B',
            source_id='dbb-slapi',
            source_event_id='match123',
            deadline=new_deadline,  # Current deadline after rescheduling
            is_active=True,
            opens_at=timezone.now(),
            reveal_at=timezone.now()
        )
        
        # Create a tip with an active lock
        tip = UserTip.objects.create(
            user=user,
            tip_type=tip_type,
            prediction_event=event,
            prediction='Team A',
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
            lock_committed_at=now - timedelta(days=1)  # Lock was placed yesterday
        )
        
        # Mock the sync_events result to include this rescheduled event
        events_result = EventSourceResult()
        events_result.events_updated = 1
        events_result.rescheduled_events = [
            RescheduledEvent(
                event=event,
                old_deadline=old_deadline,
                new_deadline=new_deadline,
                reschedule_delta=new_deadline - old_deadline
            )
        ]
        mock_event_source.sync_events.return_value = events_result
        
        out = StringIO()
        call_command('update_dbb_matches', stdout=out)
        
        output = out.getvalue()
        self.assertIn('Returning locks for rescheduled matches', output)
        
        # Verify lock was returned
        tip.refresh_from_db()
        self.assertFalse(tip.is_locked)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.NONE)
        self.assertIsNotNone(tip.lock_released_at)

    @patch('hooptipp.dbb.management.commands.update_dbb_matches.DbbEventSource')
    @patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client')
    def test_does_not_return_locks_for_normally_scheduled_far_future_matches(self, mock_build_client, mock_event_source_class):
        """Test that locks are NOT returned for matches that were always scheduled far in the future."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        mock_event_source = MagicMock()
        mock_event_source_class.return_value = mock_event_source
        
        from hooptipp.predictions.event_sources.base import EventSourceResult
        mock_event_source.sync_options.return_value = EventSourceResult()
        mock_event_source.sync_events.return_value = EventSourceResult()  # No rescheduled events
        mock_event_source.is_configured.return_value = True
        
        # Create a user
        user = User.objects.create_user(username='testuser2', email='test2@example.com', password='testpass')
        
        # Create tip type
        tip_type = TipType.objects.create(
            slug='dbb-matches',
            name='DBB Matches',
            category=TipType.TipCategory.GAME,
            is_active=True,
            default_points=1,
            deadline=timezone.now() + timedelta(days=30)
        )
        
        # Simulate a match that was always scheduled far in the future:
        # - Match is scheduled for 3 days in the future (not rescheduled)
        now = timezone.now()
        far_future_deadline = now + timedelta(days=3)  # Match scheduled for 3 days from now
        
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name='Team C vs Team D',
            source_id='dbb-slapi',
            source_event_id='match456',
            deadline=far_future_deadline,
            is_active=True,
            opens_at=timezone.now(),
            reveal_at=timezone.now()
        )
        
        # Create a tip with an active lock
        tip = UserTip.objects.create(
            user=user,
            tip_type=tip_type,
            prediction_event=event,
            prediction='Team C',
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
            lock_committed_at=now
        )
        
        out = StringIO()
        call_command('update_dbb_matches', stdout=out)
        
        output = out.getvalue()
        self.assertIn('No rescheduled matches found', output)
        
        # Verify lock was NOT returned (no rescheduled events in result)
        tip.refresh_from_db()
        self.assertTrue(tip.is_locked)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.ACTIVE)

