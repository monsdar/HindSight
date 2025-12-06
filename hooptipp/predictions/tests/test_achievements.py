"""Tests for Achievement model and achievement processing."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from io import StringIO

from hooptipp.predictions.models import (
    Achievement,
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


class AchievementModelTests(TestCase):
    """Test Achievement model functionality."""

    def setUp(self):
        """Set up test data."""
        self.user_model = get_user_model()
        self.user1 = self.user_model.objects.create_user(username='user1', password='pass')
        self.user2 = self.user_model.objects.create_user(username='user2', password='pass')
        
        self.season = Season.objects.create(
            name='Test Season',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )

    def test_achievement_creation(self):
        """Test creating an achievement."""
        achievement = Achievement.objects.create(
            user=self.user1,
            season=self.season,
            achievement_type=Achievement.AchievementType.SEASON_GOLD,
            name='Season Champion',
            description='Finished in 1st place',
            emoji='🥇',
        )
        self.assertEqual(achievement.user, self.user1)
        self.assertEqual(achievement.season, self.season)
        self.assertEqual(achievement.achievement_type, Achievement.AchievementType.SEASON_GOLD)
        self.assertEqual(achievement.name, 'Season Champion')
        self.assertEqual(achievement.emoji, '🥇')
        self.assertIsNotNone(achievement.awarded_at)

    def test_achievement_unique_constraint(self):
        """Test that unique_together constraint prevents duplicate achievements."""
        Achievement.objects.create(
            user=self.user1,
            season=self.season,
            achievement_type=Achievement.AchievementType.SEASON_GOLD,
            name='Season Champion',
            description='Finished in 1st place',
            emoji='🥇',
        )
        
        # Try to create duplicate
        with self.assertRaises(Exception):  # IntegrityError
            Achievement.objects.create(
                user=self.user1,
                season=self.season,
                achievement_type=Achievement.AchievementType.SEASON_GOLD,
                name='Season Champion',
                description='Finished in 1st place',
                emoji='🥇',
            )

    def test_achievement_str(self):
        """Test Achievement string representation."""
        achievement = Achievement.objects.create(
            user=self.user1,
            season=self.season,
            achievement_type=Achievement.AchievementType.SEASON_GOLD,
            name='Season Champion',
            description='Finished in 1st place',
            emoji='🥇',
        )
        self.assertIn(self.user1.username, str(achievement))
        self.assertIn(self.season.name, str(achievement))
        self.assertIn('Season Champion', str(achievement))

    def test_achievement_without_season(self):
        """Test that achievements can be created without a season."""
        achievement = Achievement.objects.create(
            user=self.user1,
            season=None,
            achievement_type=Achievement.AchievementType.SEASON_GOLD,
            name='Special Achievement',
            description='Some special achievement',
            emoji='🏆',
        )
        self.assertIsNone(achievement.season)


class AchievementCommandTests(TestCase):
    """Test the process_achievements management command."""

    def setUp(self):
        """Set up test data."""
        self.user_model = get_user_model()
        self.user1 = self.user_model.objects.create_user(username='user1', password='pass')
        self.user2 = self.user_model.objects.create_user(username='user2', password='pass')
        self.user3 = self.user_model.objects.create_user(username='user3', password='pass')
        self.user4 = self.user_model.objects.create_user(username='user4', password='pass')
        
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
        
        self.option1 = Option.objects.create(
            category=self.category,
            slug='test-option-1',
            name='Test Option 1'
        )
        
        self.option2 = Option.objects.create(
            category=self.category,
            slug='test-option-2',
            name='Test Option 2'
        )
        
        # Create a completed season
        today = timezone.now().date()
        self.season = Season.objects.create(
            name='Completed Season',
            start_date=today - timedelta(days=60),
            end_date=today - timedelta(days=1)  # Season ended yesterday
        )
        
        # Create events and outcomes
        self.event1 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event 1',
            points=10,
            opens_at=timezone.now() - timedelta(days=50),
            deadline=timezone.now() - timedelta(days=45),
            reveal_at=timezone.now() - timedelta(days=50),
        )
        
        self.prediction_option1 = PredictionOption.objects.create(
            event=self.event1,
            label='Option 1',
            option=self.option1,
        )
        
        self.prediction_option2 = PredictionOption.objects.create(
            event=self.event1,
            label='Option 2',
            option=self.option2,
        )
        
        self.outcome1 = EventOutcome.objects.create(
            prediction_event=self.event1,
            winning_option=self.prediction_option1,
            winning_generic_option=self.option1,
            resolved_at=timezone.now() - timedelta(days=44),
        )
        
        # Create scores for users (user1 has most points, user2 second, user3 third)
        # Use a date that's definitely within the season - use 10 days from start
        # This ensures we're well within a 60-day season
        score_date = self.season.start_date + timedelta(days=10)
        # Verify it's before season end (should always be true for a 60-day season)
        assert score_date <= self.season.end_date, f"Score date {score_date} must be <= season end {self.season.end_date}"
        score_time = timezone.make_aware(
            datetime.combine(score_date, datetime.min.time())
        )
        
        UserEventScore.objects.create(
            user=self.user1,
            prediction_event=self.event1,
            base_points=10,
            lock_multiplier=1,
            points_awarded=30,  # Highest
            awarded_at=score_time,
        )
        
        UserEventScore.objects.create(
            user=self.user2,
            prediction_event=self.event1,
            base_points=10,
            lock_multiplier=1,
            points_awarded=20,  # Second
            awarded_at=score_time,
        )
        
        UserEventScore.objects.create(
            user=self.user3,
            prediction_event=self.event1,
            base_points=10,
            lock_multiplier=1,
            points_awarded=10,  # Third
            awarded_at=score_time,
        )
        
        UserEventScore.objects.create(
            user=self.user4,
            prediction_event=self.event1,
            base_points=10,
            lock_multiplier=1,
            points_awarded=5,  # Fourth (no medal)
            awarded_at=score_time,
        )

    def test_process_season_achievements_creates_medals(self):
        """Test that the command creates gold, silver, and bronze medals."""
        # Verify scores exist (they should be created in setUp)
        from hooptipp.predictions.models import UserEventScore
        all_scores = UserEventScore.objects.all()
        self.assertGreater(all_scores.count(), 0, "Scores should exist")
        
        out = StringIO()
        call_command('process_achievements', stdout=out)
        output = out.getvalue()
        
        # Debug output
        if 'Created: 0' in output:
            print(f"\nCommand output: {output}")
            print(f"Season: {self.season.start_date} to {self.season.end_date}")
            print(f"Scores in season: {scores_in_season.count()}")
            for score in scores_in_season[:3]:
                print(f"  Score: user={score.user.username}, points={score.points_awarded}, date={score.awarded_at.date()}")
        
        # Check that achievements were created
        gold = Achievement.objects.filter(
            achievement_type=Achievement.AchievementType.SEASON_GOLD,
            user=self.user1,
            season=self.season
        )
        self.assertEqual(gold.count(), 1, f"Expected 1 gold medal, got {gold.count()}. Command output: {output}")
        
        silver = Achievement.objects.filter(
            achievement_type=Achievement.AchievementType.SEASON_SILVER,
            user=self.user2,
            season=self.season
        )
        self.assertEqual(silver.count(), 1)
        
        bronze = Achievement.objects.filter(
            achievement_type=Achievement.AchievementType.SEASON_BRONZE,
            user=self.user3,
            season=self.season
        )
        self.assertEqual(bronze.count(), 1)
        
        # User4 should not have any achievements
        user4_achievements = Achievement.objects.filter(user=self.user4)
        self.assertEqual(user4_achievements.count(), 0)

    def test_process_season_achievements_handles_ties(self):
        """Test that ties are handled correctly (all tied users get the medal)."""
        # Give user2 the same points as user1
        UserEventScore.objects.filter(user=self.user2).update(points_awarded=30)
        
        out = StringIO()
        call_command('process_achievements', stdout=out)
        
        # Both user1 and user2 should get gold
        gold_count = Achievement.objects.filter(
            achievement_type=Achievement.AchievementType.SEASON_GOLD,
            season=self.season
        ).count()
        self.assertEqual(gold_count, 2)
        
        # user3 should get bronze (since user1 and user2 tied for 1st, user3 is 3rd)
        bronze = Achievement.objects.filter(
            achievement_type=Achievement.AchievementType.SEASON_BRONZE,
            user=self.user3,
            season=self.season
        )
        self.assertEqual(bronze.count(), 1)
        
        # No silver should be awarded (since 1st place was a tie)
        silver = Achievement.objects.filter(
            achievement_type=Achievement.AchievementType.SEASON_SILVER,
            season=self.season
        )
        self.assertEqual(silver.count(), 0)

    def test_process_achievements_idempotency(self):
        """Test that running the command twice doesn't create duplicates."""
        out = StringIO()
        
        # Run first time
        call_command('process_achievements', stdout=out)
        first_count = Achievement.objects.count()
        
        # Run second time
        call_command('process_achievements', stdout=out)
        second_count = Achievement.objects.count()
        
        # Should have same number of achievements
        self.assertEqual(first_count, second_count)

    def test_process_achievements_dry_run(self):
        """Test dry-run mode doesn't create achievements."""
        out = StringIO()
        call_command('process_achievements', '--dry-run', stdout=out)
        
        # No achievements should be created
        self.assertEqual(Achievement.objects.count(), 0)
        
        # But output should indicate what would be created
        output = out.getvalue()
        self.assertIn('DRY RUN', output)

    def test_process_achievements_only_completed_seasons(self):
        """Test that only completed seasons are processed."""
        # Create an active season (non-overlapping with completed season)
        today = timezone.now().date()
        # Use dates that don't overlap with the completed season
        active_season = Season.objects.create(
            name='Active Season',
            start_date=today + timedelta(days=1),  # Starts tomorrow
            end_date=today + timedelta(days=30)  # Still active
        )
        
        out = StringIO()
        call_command('process_achievements', stdout=out)
        
        # Only achievements for completed season should exist
        achievements = Achievement.objects.all()
        for achievement in achievements:
            self.assertEqual(achievement.season, self.season)
            self.assertNotEqual(achievement.season, active_season)

    def test_process_achievements_force_flag(self):
        """Test that --force flag updates existing achievements."""
        # First run the command to create achievements
        out = StringIO()
        call_command('process_achievements', stdout=out)
        
        # Check that achievements were created
        achievements = Achievement.objects.filter(
            user=self.user1,
            season=self.season,
        )
        self.assertGreater(achievements.count(), 0, "Achievements should be created first")
        
        # Get the created achievement
        achievement = Achievement.objects.filter(
            user=self.user1,
            season=self.season,
            achievement_type=Achievement.AchievementType.SEASON_GOLD,
        ).first()
        
        if achievement:
            old_description = achievement.description
            
            # Manually change the description
            achievement.description = 'Old description'
            achievement.save()
            
            # Run command with --force
            out = StringIO()
            call_command('process_achievements', '--force', stdout=out)
            
            # Achievement should be updated
            achievement.refresh_from_db()
            self.assertNotEqual(achievement.description, 'Old description')
            self.assertIn(self.season.name, achievement.description)


class AchievementViewIntegrationTests(TestCase):
    """Test achievement integration in views."""

    def setUp(self):
        """Set up test data."""
        self.user_model = get_user_model()
        self.user1 = self.user_model.objects.create_user(username='user1', password='pass')
        self.user2 = self.user_model.objects.create_user(username='user2', password='pass')
        
        self.season = Season.objects.create(
            name='Test Season',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )
        
        # Create achievements
        self.achievement1 = Achievement.objects.create(
            user=self.user1,
            season=self.season,
            achievement_type=Achievement.AchievementType.SEASON_GOLD,
            name='Season Champion',
            description='Finished in 1st place',
            emoji='🥇',
        )
        
        self.achievement2 = Achievement.objects.create(
            user=self.user1,
            season=self.season,
            achievement_type=Achievement.AchievementType.SEASON_SILVER,
            name='Season Runner-Up',
            description='Finished in 2nd place',
            emoji='🥈',
        )
        
        # Create tip type and event for scores
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
            points=10,
            opens_at=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=1),
            reveal_at=timezone.now() - timedelta(days=1),
        )
        
        # Create a score so user appears in leaderboard
        UserEventScore.objects.create(
            user=self.user1,
            prediction_event=self.event,
            base_points=10,
            lock_multiplier=1,
            points_awarded=10,
        )
        
        UserEventScore.objects.create(
            user=self.user2,
            prediction_event=self.event,
            base_points=10,
            lock_multiplier=1,
            points_awarded=5,
        )

    def test_achievements_in_leaderboard_context(self):
        """Test that achievements are included in leaderboard rows."""
        from django.urls import reverse
        
        response = self.client.get(reverse('predictions:home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('leaderboard_rows', response.context)
        
        leaderboard_rows = response.context['leaderboard_rows']
        self.assertGreater(len(leaderboard_rows), 0)
        
        # Find user1 in leaderboard
        user1_row = None
        for row in leaderboard_rows:
            if hasattr(row, 'id') and row.id == self.user1.id:
                user1_row = row
                break
        
        self.assertIsNotNone(user1_row, "User1 should be in leaderboard")
        self.assertTrue(hasattr(user1_row, 'user_achievements'))
        self.assertEqual(len(user1_row.user_achievements), 2)
        
        # Check that achievements have season data
        for achievement in user1_row.user_achievements:
            self.assertIsNotNone(achievement.season)
            self.assertEqual(achievement.season, self.season)

    def test_achievements_empty_for_user_without_achievements(self):
        """Test that users without achievements have empty achievement list."""
        from django.urls import reverse
        
        response = self.client.get(reverse('predictions:home'))
        
        self.assertEqual(response.status_code, 200)
        leaderboard_rows = response.context['leaderboard_rows']
        
        # Find user2 in leaderboard
        user2_row = None
        for row in leaderboard_rows:
            if hasattr(row, 'id') and row.id == self.user2.id:
                user2_row = row
                break
        
        if user2_row:
            self.assertTrue(hasattr(user2_row, 'user_achievements'))
            self.assertEqual(len(user2_row.user_achievements), 0)

