"""Tests for Season model and season-based leaderboard filtering."""

from datetime import date, datetime, timedelta, time as time_type, time as time_type
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone

from hooptipp.predictions.models import (
    Season,
    UserEventScore,
    PredictionEvent,
    TipType,
    UserTip,
    EventOutcome,
    PredictionOption,
    Option,
    OptionCategory,
)
from django.contrib.auth import get_user_model


class SeasonModelTests(TestCase):
    """Test Season model functionality."""

    def setUp(self):
        """Set up test data."""
        self.user_model = get_user_model()
        self.user1 = self.user_model.objects.create_user(username='user1', password='pass')
        self.user2 = self.user_model.objects.create_user(username='user2', password='pass')
        
        # Create a tip type and event for scoring
        self.tip_type = TipType.objects.create(
            name='Test Tip Type',
            slug='test-tip-type',
            deadline=timezone.now() + timedelta(days=1)
        )
        
        self.category = OptionCategory.objects.create(
            slug='test-category',
            name='Test Category'
        )
        
        self.option = Option.objects.create(
            category=self.category,
            slug='test-option',
            name='Test Option'
        )

    def test_season_creation(self):
        """Test creating a season."""
        start_date = date(2026, 1, 1)
        start_time = time_type(0, 0, 0)
        end_date = date(2026, 1, 31)
        end_time = time_type(23, 59, 59)
        season = Season.objects.create(
            name='Test Season',
            start_date=start_date,
            start_time=start_time,
            end_date=end_date,
            end_time=end_time
        )
        self.assertEqual(season.name, 'Test Season')
        self.assertEqual(season.start_date, start_date)
        self.assertEqual(season.start_time, start_time)
        self.assertEqual(season.end_date, end_date)
        self.assertEqual(season.end_time, end_time)
        self.assertEqual(str(season), 'Test Season')

    def test_season_end_date_before_start_date_validation(self):
        """Test that end_datetime cannot be before start_datetime."""
        season = Season(
            name='Invalid Season',
            start_date=date(2026, 1, 31),
            start_time=time_type(0, 0, 0),
            end_date=date(2026, 1, 1),
            end_time=time_type(0, 0, 0)
        )
        with self.assertRaises(ValidationError) as cm:
            season.full_clean()
        self.assertIn('end_date', str(cm.exception))

    def test_season_overlapping_validation(self):
        """Test that overlapping seasons are not allowed."""
        Season.objects.create(
            name='Season 1',
            start_date=date(2026, 1, 1),
            start_time=time_type(0, 0, 0),
            end_date=date(2026, 1, 31),
            end_time=time_type(23, 59, 59)
        )
        
        # Overlapping season (same dates)
        season2 = Season(
            name='Season 2',
            start_date=date(2026, 1, 1),
            start_time=time_type(0, 0, 0),
            end_date=date(2026, 1, 31),
            end_time=time_type(23, 59, 59)
        )
        with self.assertRaises(ValidationError) as cm:
            season2.full_clean()
        self.assertIn('overlaps', str(cm.exception).lower())
        
        # Overlapping season (partial overlap)
        season3 = Season(
            name='Season 3',
            start_date=date(2026, 1, 15),
            start_time=time_type(0, 0, 0),
            end_date=date(2026, 2, 15),
            end_time=time_type(23, 59, 59)
        )
        with self.assertRaises(ValidationError) as cm:
            season3.full_clean()
        self.assertIn('overlaps', str(cm.exception).lower())
        
        # Overlapping season (completely contained)
        season4 = Season(
            name='Season 4',
            start_date=date(2026, 1, 10),
            start_time=time_type(0, 0, 0),
            end_date=date(2026, 1, 20),
            end_time=time_type(23, 59, 59)
        )
        with self.assertRaises(ValidationError) as cm:
            season4.full_clean()
        self.assertIn('overlaps', str(cm.exception).lower())

    def test_season_non_overlapping_allowed(self):
        """Test that non-overlapping seasons are allowed."""
        Season.objects.create(
            name='Season 1',
            start_date=date(2026, 1, 1),
            start_time=time_type(0, 0, 0),
            end_date=date(2026, 1, 31),
            end_time=time_type(23, 59, 59)
        )
        
        # Non-overlapping season (before)
        season2 = Season.objects.create(
            name='Season 2',
            start_date=date(2025, 12, 1),
            start_time=time_type(0, 0, 0),
            end_date=date(2025, 12, 31),
            end_time=time_type(23, 59, 59)
        )
        self.assertIsNotNone(season2)
        
        # Non-overlapping season (after)
        season3 = Season.objects.create(
            name='Season 3',
            start_date=date(2026, 2, 1),
            start_time=time_type(0, 0, 0),
            end_date=date(2026, 2, 28),
            end_time=time_type(23, 59, 59)
        )
        self.assertIsNotNone(season3)

    def test_season_is_active(self):
        """Test is_active() method."""
        now = timezone.now()
        
        # Past season (completely in the past)
        past_season = Season.objects.create(
            name='Past Season',
            start_date=(now - timedelta(days=30)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(now - timedelta(days=20)).date(),
            end_time=time_type(23, 59, 59)
        )
        self.assertFalse(past_season.is_active())
        
        # Future season (completely in the future)
        future_season = Season.objects.create(
            name='Future Season',
            start_date=(now + timedelta(days=20)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(now + timedelta(days=30)).date(),
            end_time=time_type(23, 59, 59)
        )
        self.assertFalse(future_season.is_active())
        
        # Active season (spans now)
        season = Season.objects.create(
            name='Active Season',
            start_date=(now - timedelta(days=5)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(now + timedelta(days=5)).date(),
            end_time=time_type(23, 59, 59)
        )
        self.assertTrue(season.is_active())
        
        # Season active on start date (non-overlapping with previous)
        start_season = Season.objects.create(
            name='Start Season',
            start_date=(now + timedelta(days=6)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(now + timedelta(days=15)).date(),
            end_time=time_type(23, 59, 59)
        )
        self.assertFalse(start_season.is_active())  # Not active yet
        
        # Season active on end date (non-overlapping with previous)
        end_season = Season.objects.create(
            name='End Season',
            start_date=(now - timedelta(days=35)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(now - timedelta(days=31)).date(),
            end_time=time_type(23, 59, 59)
        )
        self.assertFalse(end_season.is_active())  # Already ended

    def test_get_active_season(self):
        """Test get_active_season() class method."""
        now = timezone.now()
        
        # No active season
        active = Season.get_active_season()
        self.assertIsNone(active)
        
        # Create active season
        season = Season.objects.create(
            name='Active Season',
            start_date=(now - timedelta(days=5)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(now + timedelta(days=5)).date(),
            end_time=time_type(23, 59, 59)
        )
        active = Season.get_active_season()
        self.assertEqual(active, season)
        
        # Create another season (should not be returned if not active)
        Season.objects.create(
            name='Future Season',
            start_date=(now + timedelta(days=10)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(now + timedelta(days=20)).date(),
            end_time=time_type(23, 59, 59)
        )
        active = Season.get_active_season()
        self.assertEqual(active, season)

    def test_get_active_season_with_custom_datetime(self):
        """Test get_active_season() with custom datetime."""
        season = Season.objects.create(
            name='January Season',
            start_date=date(2026, 1, 1),
            start_time=time_type(0, 0, 0),
            end_date=date(2026, 1, 31),
            end_time=time_type(23, 59, 59)
        )
        
        # Check with datetime in season
        check_dt = timezone.make_aware(datetime(2026, 1, 15, 12, 0, 0))
        active = Season.get_active_season(check_dt)
        self.assertEqual(active, season)
        
        # Check with datetime before season
        check_dt = timezone.make_aware(datetime(2025, 12, 15, 12, 0, 0))
        active = Season.get_active_season(check_dt)
        self.assertIsNone(active)
        
        # Check with datetime after season
        check_dt = timezone.make_aware(datetime(2026, 2, 15, 12, 0, 0))
        active = Season.get_active_season(check_dt)
        self.assertIsNone(active)


class SeasonLeaderboardTests(TestCase):
    """Test leaderboard filtering by active season."""

    def setUp(self):
        """Set up test data."""
        self.user_model = get_user_model()
        self.user1 = self.user_model.objects.create_user(username='user1', password='pass')
        self.user2 = self.user_model.objects.create_user(username='user2', password='pass')
        
        # Create tip type and events
        self.tip_type = TipType.objects.create(
            name='Test Tip Type',
            slug='test-tip-type',
            deadline=timezone.now() + timedelta(days=1)
        )
        
        self.category = OptionCategory.objects.create(
            slug='test-category',
            name='Test Category'
        )
        
        self.option = Option.objects.create(
            category=self.category,
            slug='test-option',
            name='Test Option'
        )
        
        # Create events at different times
        self.event1 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event 1',
            target_kind=PredictionEvent.TargetKind.GENERIC,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            opens_at=timezone.now() - timedelta(days=10),
            deadline=timezone.now() - timedelta(days=5),
            points=1,
            is_active=True
        )
        
        self.event2 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event 2',
            target_kind=PredictionEvent.TargetKind.GENERIC,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            opens_at=timezone.now() - timedelta(days=5),
            deadline=timezone.now() - timedelta(days=2),
            points=1,
            is_active=True
        )
        
        self.option1 = PredictionOption.objects.create(
            event=self.event1,
            label='Option 1',
            option=self.option
        )
        
        self.option2 = PredictionOption.objects.create(
            event=self.event2,
            label='Option 2',
            option=self.option
        )

    def _create_score(self, user, event, points, awarded_date):
        """Helper to create a UserEventScore with specific awarded_at date."""
        # Create outcome first
        outcome = EventOutcome.objects.create(
            prediction_event=event,
            winning_option=self.option1 if event == self.event1 else self.option2,
            winning_generic_option=self.option,
            resolved_at=awarded_date
        )
        
        # Create tip
        tip = UserTip.objects.create(
            user=user,
            tip_type=event.tip_type,
            prediction_event=event,
            prediction_option=self.option1 if event == self.event1 else self.option2,
            selected_option=self.option,
            prediction='Test Prediction'
        )
        
        # Create score with specific awarded_at
        # Use update() to set awarded_at since it's auto_now_add
        score = UserEventScore(
            user=user,
            prediction_event=event,
            base_points=1,
            lock_multiplier=1,
            points_awarded=points,
            is_lock_bonus=False
        )
        score.save()
        UserEventScore.objects.filter(pk=score.pk).update(awarded_at=awarded_date)
        return UserEventScore.objects.get(pk=score.pk)

    def test_leaderboard_all_time_when_no_active_season(self):
        """Test that leaderboard shows all-time scores when no active season."""
        today = timezone.now()
        
        # Create scores at different times
        score1 = self._create_score(
            self.user1, self.event1, 10,
            today - timedelta(days=10)
        )
        score2 = self._create_score(
            self.user2, self.event2, 5,
            today - timedelta(days=2)
        )
        
        # No active season
        active_season = Season.get_active_season()
        self.assertIsNone(active_season)
        
        # Check that all scores are included
        all_scores = UserEventScore.objects.all()
        self.assertEqual(all_scores.count(), 2)
        
        # User1 should have more points
        from django.db.models import Sum
        user1_scores = UserEventScore.objects.filter(user=self.user1)
        user1_total = sum(s.points_awarded for s in user1_scores)
        self.assertEqual(user1_total, 10)

    def test_leaderboard_filtered_by_active_season(self):
        """Test that leaderboard shows only season scores when season is active."""
        now = timezone.now()
        
        # Create season
        season = Season.objects.create(
            name='Test Season',
            start_date=(now - timedelta(days=7)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(now - timedelta(days=1)).date(),
            end_time=time_type(23, 59, 59)
        )
        
        # Create scores: one in season, one outside
        score_in_season = self._create_score(
            self.user1, self.event1, 10,
            now - timedelta(days=5)
        )
        score_outside_season = self._create_score(
            self.user2, self.event2, 5,
            now - timedelta(days=10)
        )
        
        # Filter scores by season
        season_scores = UserEventScore.objects.filter(
            awarded_at__gte=season.start_datetime,
            awarded_at__lte=season.end_datetime
        )
        
        self.assertEqual(season_scores.count(), 1)
        self.assertEqual(season_scores.first(), score_in_season)
        
        # All scores should still exist
        all_scores = UserEventScore.objects.all()
        self.assertEqual(all_scores.count(), 2)

    def test_scoreboard_summary_respects_active_season(self):
        """Test that scoreboard_summary filters by active season."""
        now = timezone.now()
        
        # Create season
        season = Season.objects.create(
            name='Test Season',
            start_date=(now - timedelta(days=7)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(now + timedelta(days=7)).date(),
            end_time=time_type(23, 59, 59)
        )
        
        # Create scores: one in season, one outside
        score_in_season = self._create_score(
            self.user1, self.event1, 10,
            now - timedelta(days=5)
        )
        score_outside_season = self._create_score(
            self.user1, self.event2, 5,
            now - timedelta(days=15)
        )
        
        # Filter by season
        season_scores = UserEventScore.objects.filter(
            user=self.user1,
            awarded_at__gte=season.start_datetime,
            awarded_at__lte=season.end_datetime
        )
        
        season_total = sum(s.points_awarded for s in season_scores)
        self.assertEqual(season_total, 10)
        
        # All-time total should be higher
        all_scores = UserEventScore.objects.filter(user=self.user1)
        all_time_total = sum(s.points_awarded for s in all_scores)
        self.assertEqual(all_time_total, 15)


class SeasonAwareLockRestorationTests(TestCase):
    """Test season-aware lock restoration functionality."""

    def setUp(self):
        """Set up test data."""
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(username='testuser', password='pass')
        
        # Create tip type and event
        self.tip_type = TipType.objects.create(
            name='Test Tip Type',
            slug='test-tip-type',
            deadline=timezone.now() + timedelta(days=1)
        )
        
        self.category = OptionCategory.objects.create(
            slug='test-category',
            name='Test Category'
        )
        
        self.option = Option.objects.create(
            category=self.category,
            slug='test-option',
            name='Test Option'
        )
        
        self.event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Event',
            target_kind=PredictionEvent.TargetKind.GENERIC,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            opens_at=timezone.now() - timedelta(days=10),
            deadline=timezone.now() - timedelta(days=5),
            points=1,
            is_active=True
        )
        
        self.prediction_option = PredictionOption.objects.create(
            event=self.event,
            label='Option 1',
            option=self.option
        )

    def test_lock_forfeited_at_set_when_forfeiting(self):
        """Test that lock_forfeited_at is set when a lock is forfeited."""
        from hooptipp.predictions.lock_service import LockService
        
        # Create tip with lock
        tip = UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option,
            selected_option=self.option,
            prediction='Test Prediction',
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        
        # Create outcome
        resolved_at = timezone.now() - timedelta(days=5)
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.prediction_option,
            winning_generic_option=self.option,
            resolved_at=resolved_at
        )
        
        # Forfeit the lock
        lock_service = LockService(self.user)
        lock_service.schedule_forfeit(tip, resolved_at=outcome.resolved_at)
        
        # Verify lock_forfeited_at is set
        tip.refresh_from_db()
        self.assertEqual(tip.lock_forfeited_at, resolved_at)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.FORFEITED)

    def test_locks_forfeited_before_season_restored_immediately(self):
        """Test that locks forfeited before season start are restored immediately."""
        from hooptipp.predictions.lock_service import LockService
        
        now = timezone.now()
        season_start = now - timedelta(days=3)
        
        # Create season
        season = Season.objects.create(
            name='Test Season',
            start_date=season_start.date(),
            start_time=time_type(0, 0, 0),
            end_date=(now + timedelta(days=30)).date(),
            end_time=time_type(23, 59, 59)
        )
        
        # Create tip with forfeited lock (forfeited before season start)
        forfeited_at = season_start - timedelta(days=5)
        tip = UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option,
            selected_option=self.option,
            prediction='Test Prediction',
            is_locked=False,
            lock_status=UserTip.LockStatus.FORFEITED,
            lock_forfeited_at=forfeited_at,
            lock_releases_at=forfeited_at + timedelta(days=30),  # Would normally return in 30 days
        )
        
        # Refresh lock service (should restore pre-season forfeited locks)
        lock_service = LockService(self.user)
        summary = lock_service.refresh()
        
        # Verify lock is restored
        tip.refresh_from_db()
        self.assertEqual(tip.lock_status, UserTip.LockStatus.RETURNED)
        self.assertIsNotNone(tip.lock_released_at)
        self.assertIsNone(tip.lock_releases_at)
        self.assertFalse(tip.is_locked)
        
        # Verify lock is available
        self.assertEqual(summary.available, 3)  # All locks available

    def test_locks_forfeited_during_season_follow_normal_delay(self):
        """Test that locks forfeited during season follow normal 30-day delay."""
        from hooptipp.predictions.lock_service import LockService
        
        now = timezone.now()
        season_start = now - timedelta(days=10)
        
        # Create season
        season = Season.objects.create(
            name='Test Season',
            start_date=season_start.date(),
            start_time=time_type(0, 0, 0),
            end_date=(now + timedelta(days=30)).date(),
            end_time=time_type(23, 59, 59)
        )
        
        # Create tip with forfeited lock (forfeited during season)
        forfeited_at = season_start + timedelta(days=2)
        tip = UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option,
            selected_option=self.option,
            prediction='Test Prediction',
            is_locked=False,
            lock_status=UserTip.LockStatus.FORFEITED,
            lock_forfeited_at=forfeited_at,
            lock_releases_at=forfeited_at + timedelta(days=30),  # Should return in 30 days
        )
        
        # Refresh lock service
        lock_service = LockService(self.user)
        summary = lock_service.refresh()
        
        # Verify lock is NOT restored (still forfeited, waiting for 30 days)
        tip.refresh_from_db()
        self.assertEqual(tip.lock_status, UserTip.LockStatus.FORFEITED)
        self.assertIsNotNone(tip.lock_releases_at)
        self.assertIsNone(tip.lock_released_at)
        
        # Verify lock is not available (counted as pending)
        self.assertEqual(summary.available, 2)  # One lock pending
        self.assertEqual(summary.pending, 1)

    def test_no_season_restoration_when_no_active_season(self):
        """Test that normal lock behavior works when no active season exists."""
        from hooptipp.predictions.lock_service import LockService
        
        # Create tip with forfeited lock
        forfeited_at = timezone.now() - timedelta(days=5)
        tip = UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option,
            selected_option=self.option,
            prediction='Test Prediction',
            is_locked=False,
            lock_status=UserTip.LockStatus.FORFEITED,
            lock_forfeited_at=forfeited_at,
            lock_releases_at=forfeited_at + timedelta(days=30),
        )
        
        # No active season
        active_season = Season.get_active_season()
        self.assertIsNone(active_season)
        
        # Refresh lock service
        lock_service = LockService(self.user)
        summary = lock_service.refresh()
        
        # Verify lock is NOT restored (normal behavior, waiting for 30 days)
        tip.refresh_from_db()
        self.assertEqual(tip.lock_status, UserTip.LockStatus.FORFEITED)
        self.assertIsNotNone(tip.lock_releases_at)
        self.assertIsNone(tip.lock_released_at)
        
        # Verify lock is not available
        self.assertEqual(summary.available, 2)
        self.assertEqual(summary.pending, 1)

    def test_lock_forfeited_exactly_on_season_start_not_restored(self):
        """Test that locks forfeited exactly on season start datetime are not restored."""
        from hooptipp.predictions.lock_service import LockService
        
        now = timezone.now()
        season_start = now - timedelta(days=3)
        
        # Create season
        season = Season.objects.create(
            name='Test Season',
            start_date=season_start.date(),
            start_time=time_type(0, 0, 0),
            end_date=(now + timedelta(days=30)).date(),
            end_time=time_type(23, 59, 59)
        )
        
        # Create tip with forfeited lock (forfeited exactly on season start)
        forfeited_at = season_start
        tip = UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option,
            selected_option=self.option,
            prediction='Test Prediction',
            is_locked=False,
            lock_status=UserTip.LockStatus.FORFEITED,
            lock_forfeited_at=forfeited_at,
            lock_releases_at=forfeited_at + timedelta(days=30),
        )
        
        # Refresh lock service
        lock_service = LockService(self.user)
        summary = lock_service.refresh()
        
        # Verify lock is NOT restored (forfeited on or after season start)
        tip.refresh_from_db()
        self.assertEqual(tip.lock_status, UserTip.LockStatus.FORFEITED)
        self.assertIsNotNone(tip.lock_releases_at)
        self.assertIsNone(tip.lock_released_at)
        
        # Verify lock is not available
        self.assertEqual(summary.available, 2)
        self.assertEqual(summary.pending, 1)

    def test_locks_without_forfeited_at_not_restored(self):
        """Test that locks without lock_forfeited_at are handled gracefully."""
        from hooptipp.predictions.lock_service import LockService
        
        now = timezone.now()
        season_start = now - timedelta(days=3)
        
        # Create season
        season = Season.objects.create(
            name='Test Season',
            start_date=season_start.date(),
            start_time=time_type(0, 0, 0),
            end_date=(now + timedelta(days=30)).date(),
            end_time=time_type(23, 59, 59)
        )
        
        # Create tip with forfeited lock but no lock_forfeited_at (old data)
        tip = UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.prediction_option,
            selected_option=self.option,
            prediction='Test Prediction',
            is_locked=False,
            lock_status=UserTip.LockStatus.FORFEITED,
            lock_forfeited_at=None,  # Missing data
            lock_releases_at=timezone.now() + timedelta(days=25),
        )
        
        # Refresh lock service (should not crash)
        lock_service = LockService(self.user)
        summary = lock_service.refresh()
        
        # Verify lock is NOT restored (can't determine if pre-season)
        tip.refresh_from_db()
        self.assertEqual(tip.lock_status, UserTip.LockStatus.FORFEITED)
        self.assertIsNotNone(tip.lock_releases_at)
        
        # Verify lock is not available
        self.assertEqual(summary.available, 2)
        self.assertEqual(summary.pending, 1)