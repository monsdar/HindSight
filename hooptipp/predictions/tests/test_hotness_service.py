from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from datetime import timedelta

from ..models import (
    UserHotness, HotnessKudos, Season, PredictionEvent, EventOutcome,
    UserTip, UserEventScore, TipType, OptionCategory, Option, PredictionOption
)
from ..hotness_service import (
    give_kudos, award_hotness_for_correct_prediction, get_or_create_hotness,
    HOTNESS_CORRECT_PREDICTION, HOTNESS_STREAK_BONUS, STREAK_LENGTH
)

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
    
    def test_streak_bonus_awarded_for_consecutive_correct_predictions(self):
        """Test that streak bonus is awarded when last 3 predictions are all correct."""
        # Create tip type and category
        tip_type = TipType.objects.create(
            name="Test Type",
            slug="test-type",
            category=TipType.TipCategory.GAME,
            default_points=1,
            deadline=timezone.now() + timedelta(days=1),
            is_active=True,
        )
        category = OptionCategory.objects.create(slug='test', name='Test')
        option = Option.objects.create(category=category, slug='opt1', name='Option 1')
        
        # Create 3 events with outcomes
        events = []
        outcomes = []
        for i in range(3):
            event = PredictionEvent.objects.create(
                tip_type=tip_type,
                name=f"Event {i+1}",
                target_kind=PredictionEvent.TargetKind.GENERIC,
                selection_mode=PredictionEvent.SelectionMode.CURATED,
                points=1,
                opens_at=timezone.now() - timedelta(days=10-i),
                deadline=timezone.now() - timedelta(days=9-i),
                is_active=True,
            )
            pred_option = PredictionOption.objects.create(
                event=event,
                label='Option 1',
                option=option
            )
            outcome = EventOutcome.objects.create(
                prediction_event=event,
                winning_option=pred_option,
                winning_generic_option=option,
                resolved_at=timezone.now() - timedelta(hours=3-i),  # Most recent first
            )
            events.append(event)
            outcomes.append(outcome)
            
            # Create tip for user
            UserTip.objects.create(
                user=self.user1,
                tip_type=tip_type,
                prediction_event=event,
                prediction_option=pred_option,
                selected_option=option,
                prediction='Test'
            )
            
            # Create score (correct prediction)
            UserEventScore.objects.create(
                user=self.user1,
                prediction_event=event,
                base_points=1,
                lock_multiplier=1,
                points_awarded=1,
            )
        
        # Award hotness for the third correct prediction
        initial_score = get_or_create_hotness(self.user1, self.season).score
        award_hotness_for_correct_prediction(self.user1, season=self.season)
        
        hotness = UserHotness.objects.get(user=self.user1, season=self.season)
        # Should get base hotness + streak bonus
        expected_score = initial_score + HOTNESS_CORRECT_PREDICTION + HOTNESS_STREAK_BONUS
        self.assertEqual(hotness.score, expected_score)
    
    def test_streak_bonus_not_awarded_when_incorrect_prediction_in_between(self):
        """Test that streak bonus is NOT awarded when there's an incorrect prediction in between."""
        # Create tip type and category
        tip_type = TipType.objects.create(
            name="Test Type",
            slug="test-type",
            category=TipType.TipCategory.GAME,
            default_points=1,
            deadline=timezone.now() + timedelta(days=1),
            is_active=True,
        )
        category = OptionCategory.objects.create(slug='test', name='Test')
        option1 = Option.objects.create(category=category, slug='opt1', name='Option 1')
        option2 = Option.objects.create(category=category, slug='opt2', name='Option 2')
        
        # Create 4 events with outcomes
        # Pattern: Correct, Correct, Wrong, Correct (most recent first)
        events = []
        for i in range(4):
            event = PredictionEvent.objects.create(
                tip_type=tip_type,
                name=f"Event {i+1}",
                target_kind=PredictionEvent.TargetKind.GENERIC,
                selection_mode=PredictionEvent.SelectionMode.CURATED,
                points=1,
                opens_at=timezone.now() - timedelta(days=10-i),
                deadline=timezone.now() - timedelta(days=9-i),
                is_active=True,
            )
            pred_option1 = PredictionOption.objects.create(
                event=event,
                label='Option 1',
                option=option1
            )
            pred_option2 = PredictionOption.objects.create(
                event=event,
                label='Option 2',
                option=option2
            )
            
            # Outcome always wins with option1
            EventOutcome.objects.create(
                prediction_event=event,
                winning_option=pred_option1,
                winning_generic_option=option1,
                resolved_at=timezone.now() - timedelta(hours=4-i),
            )
            events.append(event)
            
            # Create tip - user picks option1 for events 0, 1, 3 (correct) and option2 for event 2 (wrong)
            if i == 2:  # Wrong prediction
                UserTip.objects.create(
                    user=self.user1,
                    tip_type=tip_type,
                    prediction_event=event,
                    prediction_option=pred_option2,
                    selected_option=option2,
                    prediction='Wrong'
                )
                # No UserEventScore created for wrong prediction
            else:  # Correct predictions
                UserTip.objects.create(
                    user=self.user1,
                    tip_type=tip_type,
                    prediction_event=event,
                    prediction_option=pred_option1,
                    selected_option=option1,
                    prediction='Correct'
                )
                UserEventScore.objects.create(
                    user=self.user1,
                    prediction_event=event,
                    base_points=1,
                    lock_multiplier=1,
                    points_awarded=1,
                )
        
        # Award hotness for the most recent correct prediction (event 0)
        initial_score = get_or_create_hotness(self.user1, self.season).score
        award_hotness_for_correct_prediction(self.user1, season=self.season)
        
        hotness = UserHotness.objects.get(user=self.user1, season=self.season)
        # Should get base hotness but NO streak bonus (because event 2 was wrong)
        expected_score = initial_score + HOTNESS_CORRECT_PREDICTION
        self.assertEqual(hotness.score, expected_score)
    
    def test_streak_bonus_not_awarded_when_fewer_than_streak_length(self):
        """Test that streak bonus is NOT awarded when there are fewer than STREAK_LENGTH resolved predictions."""
        # Create tip type and category
        tip_type = TipType.objects.create(
            name="Test Type",
            slug="test-type",
            category=TipType.TipCategory.GAME,
            default_points=1,
            deadline=timezone.now() + timedelta(days=1),
            is_active=True,
        )
        category = OptionCategory.objects.create(slug='test', name='Test')
        option = Option.objects.create(category=category, slug='opt1', name='Option 1')
        
        # Create only 2 events (less than STREAK_LENGTH which is 3)
        for i in range(2):
            event = PredictionEvent.objects.create(
                tip_type=tip_type,
                name=f"Event {i+1}",
                target_kind=PredictionEvent.TargetKind.GENERIC,
                selection_mode=PredictionEvent.SelectionMode.CURATED,
                points=1,
                opens_at=timezone.now() - timedelta(days=10-i),
                deadline=timezone.now() - timedelta(days=9-i),
                is_active=True,
            )
            pred_option = PredictionOption.objects.create(
                event=event,
                label='Option 1',
                option=option
            )
            EventOutcome.objects.create(
                prediction_event=event,
                winning_option=pred_option,
                winning_generic_option=option,
                resolved_at=timezone.now() - timedelta(hours=2-i),
            )
            
            UserTip.objects.create(
                user=self.user1,
                tip_type=tip_type,
                prediction_event=event,
                prediction_option=pred_option,
                selected_option=option,
                prediction='Test'
            )
            
            UserEventScore.objects.create(
                user=self.user1,
                prediction_event=event,
                base_points=1,
                lock_multiplier=1,
                points_awarded=1,
            )
        
        # Award hotness for the second correct prediction
        initial_score = get_or_create_hotness(self.user1, self.season).score
        award_hotness_for_correct_prediction(self.user1, season=self.season)
        
        hotness = UserHotness.objects.get(user=self.user1, season=self.season)
        # Should get base hotness but NO streak bonus (only 2 predictions, need 3)
        expected_score = initial_score + HOTNESS_CORRECT_PREDICTION
        self.assertEqual(hotness.score, expected_score)

