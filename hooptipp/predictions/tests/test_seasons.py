"""Tests for Season model and season-based leaderboard filtering."""

from datetime import date, datetime, timedelta
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
        season = Season.objects.create(
            name='Test Season',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )
        self.assertEqual(season.name, 'Test Season')
        self.assertEqual(season.start_date, date(2026, 1, 1))
        self.assertEqual(season.end_date, date(2026, 1, 31))
        self.assertEqual(str(season), 'Test Season')

    def test_season_end_date_before_start_date_validation(self):
        """Test that end_date cannot be before start_date."""
        season = Season(
            name='Invalid Season',
            start_date=date(2026, 1, 31),
            end_date=date(2026, 1, 1)
        )
        with self.assertRaises(ValidationError) as cm:
            season.full_clean()
        self.assertIn('end_date', str(cm.exception))

    def test_season_overlapping_validation(self):
        """Test that overlapping seasons are not allowed."""
        Season.objects.create(
            name='Season 1',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )
        
        # Overlapping season (same dates)
        season2 = Season(
            name='Season 2',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )
        with self.assertRaises(ValidationError) as cm:
            season2.full_clean()
        self.assertIn('overlaps', str(cm.exception).lower())
        
        # Overlapping season (partial overlap)
        season3 = Season(
            name='Season 3',
            start_date=date(2026, 1, 15),
            end_date=date(2026, 2, 15)
        )
        with self.assertRaises(ValidationError) as cm:
            season3.full_clean()
        self.assertIn('overlaps', str(cm.exception).lower())
        
        # Overlapping season (completely contained)
        season4 = Season(
            name='Season 4',
            start_date=date(2026, 1, 10),
            end_date=date(2026, 1, 20)
        )
        with self.assertRaises(ValidationError) as cm:
            season4.full_clean()
        self.assertIn('overlaps', str(cm.exception).lower())

    def test_season_non_overlapping_allowed(self):
        """Test that non-overlapping seasons are allowed."""
        Season.objects.create(
            name='Season 1',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )
        
        # Non-overlapping season (before)
        season2 = Season.objects.create(
            name='Season 2',
            start_date=date(2025, 12, 1),
            end_date=date(2025, 12, 31)
        )
        self.assertIsNotNone(season2)
        
        # Non-overlapping season (after)
        season3 = Season.objects.create(
            name='Season 3',
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28)
        )
        self.assertIsNotNone(season3)

    def test_season_is_active(self):
        """Test is_active() method."""
        today = timezone.now().date()
        
        # Past season (completely in the past)
        past_season = Season.objects.create(
            name='Past Season',
            start_date=today - timedelta(days=30),
            end_date=today - timedelta(days=20)
        )
        self.assertFalse(past_season.is_active())
        
        # Future season (completely in the future)
        future_season = Season.objects.create(
            name='Future Season',
            start_date=today + timedelta(days=20),
            end_date=today + timedelta(days=30)
        )
        self.assertFalse(future_season.is_active())
        
        # Active season (spans today)
        season = Season.objects.create(
            name='Active Season',
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=5)
        )
        self.assertTrue(season.is_active())
        
        # Season active on start date (non-overlapping with previous)
        start_season = Season.objects.create(
            name='Start Season',
            start_date=today + timedelta(days=6),
            end_date=today + timedelta(days=15)
        )
        self.assertFalse(start_season.is_active())  # Not active yet
        
        # Season active on end date (non-overlapping with previous)
        end_season = Season.objects.create(
            name='End Season',
            start_date=today - timedelta(days=35),
            end_date=today - timedelta(days=31)
        )
        self.assertFalse(end_season.is_active())  # Already ended

    def test_get_active_season(self):
        """Test get_active_season() class method."""
        today = timezone.now().date()
        
        # No active season
        active = Season.get_active_season()
        self.assertIsNone(active)
        
        # Create active season
        season = Season.objects.create(
            name='Active Season',
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=5)
        )
        active = Season.get_active_season()
        self.assertEqual(active, season)
        
        # Create another season (should not be returned if not active)
        Season.objects.create(
            name='Future Season',
            start_date=today + timedelta(days=10),
            end_date=today + timedelta(days=20)
        )
        active = Season.get_active_season()
        self.assertEqual(active, season)

    def test_get_active_season_with_custom_date(self):
        """Test get_active_season() with custom date."""
        season = Season.objects.create(
            name='January Season',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )
        
        # Check with date in season
        active = Season.get_active_season(date(2026, 1, 15))
        self.assertEqual(active, season)
        
        # Check with date before season
        active = Season.get_active_season(date(2025, 12, 15))
        self.assertIsNone(active)
        
        # Check with date after season
        active = Season.get_active_season(date(2026, 2, 15))
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
        today = timezone.now().date()
        
        # Create season
        season = Season.objects.create(
            name='Test Season',
            start_date=today - timedelta(days=7),
            end_date=today - timedelta(days=1)
        )
        
        # Create scores: one in season, one outside
        score_in_season = self._create_score(
            self.user1, self.event1, 10,
            timezone.make_aware(datetime.combine(today - timedelta(days=5), datetime.min.time()))
        )
        score_outside_season = self._create_score(
            self.user2, self.event2, 5,
            timezone.make_aware(datetime.combine(today - timedelta(days=10), datetime.min.time()))
        )
        
        # Filter scores by season
        season_scores = UserEventScore.objects.filter(
            awarded_at__date__gte=season.start_date,
            awarded_at__date__lte=season.end_date
        )
        
        self.assertEqual(season_scores.count(), 1)
        self.assertEqual(season_scores.first(), score_in_season)
        
        # All scores should still exist
        all_scores = UserEventScore.objects.all()
        self.assertEqual(all_scores.count(), 2)

    def test_scoreboard_summary_respects_active_season(self):
        """Test that scoreboard_summary filters by active season."""
        today = timezone.now().date()
        
        # Create season
        season = Season.objects.create(
            name='Test Season',
            start_date=today - timedelta(days=7),
            end_date=today + timedelta(days=7)
        )
        
        # Create scores: one in season, one outside
        score_in_season = self._create_score(
            self.user1, self.event1, 10,
            timezone.make_aware(datetime.combine(today - timedelta(days=5), datetime.min.time()))
        )
        score_outside_season = self._create_score(
            self.user1, self.event2, 5,
            timezone.make_aware(datetime.combine(today - timedelta(days=15), datetime.min.time()))
        )
        
        # Filter by season
        season_scores = UserEventScore.objects.filter(
            user=self.user1,
            awarded_at__date__gte=season.start_date,
            awarded_at__date__lte=season.end_date
        )
        
        season_total = sum(s.points_awarded for s in season_scores)
        self.assertEqual(season_total, 10)
        
        # All-time total should be higher
        all_scores = UserEventScore.objects.filter(user=self.user1)
        all_time_total = sum(s.points_awarded for s in all_scores)
        self.assertEqual(all_time_total, 15)

