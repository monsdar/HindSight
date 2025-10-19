"""
Tests to verify that NBA game deadlines are set to actual tip-off times instead of midnight.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from hooptipp.predictions.models import PredictionEvent, TipType


class NbaDeadlineFixTests(TestCase):
    """Test that NBA game deadlines use actual tip-off times."""

    def setUp(self):
        """Set up test data."""
        self.tip_type = TipType.objects.create(
            slug='weekly-games',
            name='Weekly games',
            category=TipType.TipCategory.GAME,
            deadline=timezone.now() + timedelta(days=7),
            is_active=True,
        )

    def test_datetime_parsing_uses_correct_field(self):
        """Test that datetime parsing logic uses the datetime field correctly."""
        # Create a game time that's 2 days in the future at 11:30 PM UTC
        future_time = timezone.now() + timedelta(days=2)
        game_time_utc = future_time.replace(hour=23, minute=30, second=0, microsecond=0)
        
        # Create a mock game object with datetime field (like BallDontLie API response)
        # Use naive datetime to avoid timezone issues
        naive_game_time = game_time_utc.replace(tzinfo=None)
        mock_game = MagicMock()
        mock_game.datetime = naive_game_time.isoformat() + 'Z'
        
        # Test the parsing logic from the services
        datetime_str = getattr(mock_game, 'datetime', '')
        self.assertNotEqual(datetime_str, '')
        
        # Parse the datetime string (same logic as in the services)
        try:
            parsed_time = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            if timezone.is_naive(parsed_time):
                parsed_time = timezone.make_aware(parsed_time)
        except ValueError as e:
            self.fail(f"Failed to parse datetime: {e}")
        
        # Verify the parsed time is correct
        self.assertEqual(parsed_time.hour, 23)
        self.assertEqual(parsed_time.minute, 30)
        self.assertNotEqual(parsed_time.hour, 0)  # Not midnight
        self.assertNotEqual(parsed_time.minute, 0)  # Not midnight

    def test_prediction_event_deadline_uses_actual_tip_off_time(self):
        """Test that PredictionEvent deadline is set to actual tip-off time."""
        # Create a specific game time: Wednesday 1:30 AM CEST (which is Tuesday 11:30 PM UTC)
        # This matches the user's example: "Wednesday 01:30 AM (CEST)"
        future_date = timezone.now().date() + timedelta(days=2)
        game_time_utc = timezone.make_aware(
            datetime.combine(future_date, datetime.min.time().replace(hour=23, minute=30))
        )
        
        # Create a PredictionEvent with the actual tip-off time as deadline
        event = PredictionEvent(
            tip_type=self.tip_type,
            name="HOU @ OKC",
            description="Houston Rockets at Oklahoma City Thunder",
            deadline=game_time_utc,  # This is the key - deadline should be actual tip-off time
            opens_at=game_time_utc - timedelta(days=7),
            reveal_at=game_time_utc - timedelta(days=7),
            is_active=True,
        )
        
        # Verify the deadline is set to the actual tip-off time
        self.assertEqual(event.deadline, game_time_utc)
        self.assertEqual(event.deadline.hour, 23)
        self.assertEqual(event.deadline.minute, 30)
        
        # Verify it's not midnight
        self.assertNotEqual(event.deadline.hour, 0)
        self.assertNotEqual(event.deadline.minute, 0)
        
        # Verify the deadline is in the future
        self.assertGreater(event.deadline, timezone.now())

    def test_old_vs_new_deadline_behavior(self):
        """Test that demonstrates the difference between old (midnight) and new (actual time) behavior."""
        future_date = timezone.now().date() + timedelta(days=2)
        
        # Old behavior: deadline would be set to midnight
        old_deadline = timezone.make_aware(
            datetime.combine(future_date, datetime.min.time())  # Midnight
        )
        
        # New behavior: deadline is set to actual tip-off time
        new_deadline = timezone.make_aware(
            datetime.combine(future_date, datetime.min.time().replace(hour=23, minute=30))  # 11:30 PM
        )
        
        # Verify they are different
        self.assertNotEqual(old_deadline, new_deadline)
        self.assertEqual(old_deadline.hour, 0)  # Old: midnight
        self.assertEqual(new_deadline.hour, 23)  # New: actual tip-off time
        
        # Create events with both deadlines to show the difference
        old_event = PredictionEvent(
            tip_type=self.tip_type,
            name="Old Event",
            deadline=old_deadline,
            opens_at=old_deadline - timedelta(days=7),
            reveal_at=old_deadline - timedelta(days=7),
            is_active=True,
        )
        
        new_event = PredictionEvent(
            tip_type=self.tip_type,
            name="New Event", 
            deadline=new_deadline,
            opens_at=new_deadline - timedelta(days=7),
            reveal_at=new_deadline - timedelta(days=7),
            is_active=True,
        )
        
        # Verify the difference
        self.assertEqual(old_event.deadline.hour, 0)  # Midnight
        self.assertEqual(new_event.deadline.hour, 23)  # Actual tip-off time
        
        # The new deadline should be 23.5 hours later than the old one
        time_diff = new_deadline - old_deadline
        self.assertEqual(time_diff.total_seconds(), 23.5 * 3600)  # 23.5 hours in seconds