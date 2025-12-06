from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from datetime import timedelta

from ..models import UserHotness, HotnessKudos, Season
from ..hotness_service import give_kudos, award_hotness_for_correct_prediction, get_or_create_hotness

User = get_user_model()


class HotnessServiceTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1')
        self.user2 = User.objects.create_user(username='user2')
        self.season = Season.objects.create(
            name='Test Season',
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30)
        )
    
    def test_give_kudos_success(self):
        result = give_kudos(self.user1, self.user2)
        self.assertTrue(result['success'])
        self.assertEqual(HotnessKudos.objects.count(), 1)
        
        hotness = UserHotness.objects.get(user=self.user2)
        self.assertGreater(hotness.score, 0)
    
    def test_give_kudos_to_self_fails(self):
        result = give_kudos(self.user1, self.user1)
        self.assertFalse(result['success'])
        self.assertEqual(HotnessKudos.objects.count(), 0)
    
    def test_give_kudos_twice_same_day_fails(self):
        give_kudos(self.user1, self.user2)
        result = give_kudos(self.user1, self.user2)
        self.assertFalse(result['success'])
        self.assertEqual(HotnessKudos.objects.count(), 1)
    
    def test_admin_can_give_unlimited_kudos(self):
        """Test that admin users can give unlimited kudos (for testing)."""
        # Make user1 an admin
        self.user1.is_staff = True
        self.user1.save()
        
        # Give kudos multiple times
        result1 = give_kudos(self.user1, self.user2)
        self.assertTrue(result1['success'])
        
        result2 = give_kudos(self.user1, self.user2)
        self.assertTrue(result2['success'])
        
        result3 = give_kudos(self.user1, self.user2)
        self.assertTrue(result3['success'])
        
        # All three kudos should be recorded
        self.assertEqual(HotnessKudos.objects.count(), 3)
    
    def test_hotness_decay_with_default_rate(self):
        """Test decay with default rate of 0.1 per hour."""
        # Create hotness without calling get_or_create to avoid automatic decay
        hotness = UserHotness.objects.create(
            user=self.user1,
            season=self.season,
            score=50.0
        )
        # Update last_decay to a past time (auto_now_add prevents setting it in create)
        UserHotness.objects.filter(pk=hotness.pk).update(
            last_decay=timezone.now() - timedelta(hours=10)
        )
        hotness.refresh_from_db()
        
        hotness.decay()
        # Should lose 10 hours * 0.1 = 1.0 hotness
        self.assertAlmostEqual(hotness.score, 49.0, places=1)
    
    def test_hotness_decay_respects_setting(self):
        """Test that decay uses HOTNESS_DECAY_PER_HOUR setting."""
        # Store original setting
        original_decay = settings.HOTNESS_DECAY_PER_HOUR
        
        # Create hotness without calling get_or_create to avoid automatic decay
        hotness = UserHotness.objects.create(
            user=self.user1,
            season=self.season,
            score=100.0
        )
        # Update last_decay to a past time (auto_now_add prevents setting it in create)
        UserHotness.objects.filter(pk=hotness.pk).update(
            last_decay=timezone.now() - timedelta(hours=5)
        )
        hotness.refresh_from_db()
        
        # Apply decay
        hotness.decay()
        
        # Should lose 5 hours * HOTNESS_DECAY_PER_HOUR
        expected_loss = 5 * original_decay
        expected_score = 100.0 - expected_loss
        self.assertAlmostEqual(hotness.score, expected_score, places=1)
    
    def test_hotness_levels(self):
        hotness = get_or_create_hotness(self.user1, self.season)
        
        hotness.score = 5.0
        self.assertEqual(hotness.get_level(), 0)
        
        hotness.score = 15.0
        self.assertEqual(hotness.get_level(), 1)
        
        hotness.score = 30.0
        self.assertEqual(hotness.get_level(), 2)
        
        hotness.score = 60.0
        self.assertEqual(hotness.get_level(), 3)
        
        hotness.score = 110.0
        self.assertEqual(hotness.get_level(), 4)
    
    def test_score_uses_float(self):
        """Test that scores can be fractional."""
        hotness = get_or_create_hotness(self.user1, self.season)
        hotness.score = 12.5
        hotness.save()
        
        hotness.refresh_from_db()
        self.assertEqual(hotness.score, 12.5)
    
    def test_hotness_decay_never_goes_negative(self):
        """Test that decay stops at 0."""
        # Create hotness without calling get_or_create to avoid automatic decay
        hotness = UserHotness.objects.create(
            user=self.user1,
            season=self.season,
            score=1.0
        )
        # Update last_decay to a past time (auto_now_add prevents setting it in create)
        UserHotness.objects.filter(pk=hotness.pk).update(
            last_decay=timezone.now() - timedelta(hours=100)
        )
        hotness.refresh_from_db()
        
        hotness.decay()
        self.assertEqual(hotness.score, 0.0)
    
    def test_kudos_creates_season_link(self):
        """Test that kudos are linked to the active season."""
        result = give_kudos(self.user1, self.user2)
        self.assertTrue(result['success'])
        
        kudos = HotnessKudos.objects.first()
        self.assertEqual(kudos.season, self.season)
    
    def test_hotness_for_different_seasons(self):
        """Test that users can have different hotness scores for different seasons."""
        # Create hotness for current season
        hotness1 = get_or_create_hotness(self.user1, self.season)
        hotness1.score = 50.0
        hotness1.save()
        
        # Create another season
        season2 = Season.objects.create(
            name='Season 2',
            start_date=self.season.end_date + timedelta(days=1),
            end_date=self.season.end_date + timedelta(days=60)
        )
        
        # Create hotness for second season
        hotness2 = get_or_create_hotness(self.user1, season2)
        hotness2.score = 25.0
        hotness2.save()
        
        # Verify both exist with different scores
        self.assertEqual(UserHotness.objects.filter(user=self.user1).count(), 2)
        self.assertEqual(hotness1.score, 50.0)
        self.assertEqual(hotness2.score, 25.0)

