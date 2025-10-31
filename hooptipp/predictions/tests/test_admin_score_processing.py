"""Tests for the admin score processing functionality."""

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

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


class AdminScoreProcessingTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        
        # Create admin user
        self.admin_user = self.user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password"
        )
        
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
        )
        self.celtics_option_obj = Option.objects.create(
            category=self.teams_cat,
            slug='bos',
            name='Boston Celtics',
            short_name='BOS',
            external_id='2',
        )
        
        # Create PredictionOptions
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
        
        self.client = Client()

    def test_process_all_scores_admin_view_requires_post(self) -> None:
        """Test that the admin view only accepts POST requests."""
        self.client.force_login(self.admin_user)
        
        # Try GET request
        url = reverse('admin:predictions_usereventscore_process_all_scores')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)  # Method Not Allowed

    def test_process_all_scores_admin_view_requires_permission(self) -> None:
        """Test that the admin view requires change permission."""
        # Create regular user without admin permissions
        regular_user = self.user_model.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="password"
        )
        self.client.force_login(regular_user)
        
        url = reverse('admin:predictions_usereventscore_process_all_scores')
        response = self.client.post(url)
        # Django admin redirects to login page for users without permissions
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_process_all_scores_admin_view_creates_scores(self) -> None:
        """Test that the admin view successfully processes scores."""
        self.client.force_login(self.admin_user)
        
        # Create a user and tip
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
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
        
        # Create outcome
        EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )
        
        # Process scores via admin
        url = reverse('admin:predictions_usereventscore_process_all_scores')
        response = self.client.post(url)
        
        # Should redirect back to changelist
        self.assertEqual(response.status_code, 302)
        self.assertIn('usereventscore/', response.url)
        
        # Should create a score
        self.assertEqual(UserEventScore.objects.count(), 1)
        score = UserEventScore.objects.get()
        self.assertEqual(score.user, user)
        self.assertEqual(score.points_awarded, 3)
        
        # Should not return or forfeit any locks (no lock on this tip)
        tip = UserTip.objects.get()
        self.assertFalse(tip.is_locked)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.NONE)

    def test_process_all_scores_admin_view_with_force(self) -> None:
        """Test that the admin view handles force parameter correctly."""
        self.client.force_login(self.admin_user)
        
        # Create a user and tip
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
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
        
        # Create outcome
        EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )
        
        # Create existing score
        existing_score = UserEventScore.objects.create(
            user=user,
            prediction_event=self.event,
            base_points=1,
            lock_multiplier=1,
            points_awarded=1,
        )
        
        # Process scores with force=True
        url = reverse('admin:predictions_usereventscore_process_all_scores')
        response = self.client.post(url, {'force': '1'})
        
        # Should redirect back to changelist
        self.assertEqual(response.status_code, 302)
        
        # Should delete old score and create new one
        self.assertEqual(UserEventScore.objects.count(), 1)
        new_score = UserEventScore.objects.get()
        self.assertNotEqual(new_score.id, existing_score.id)
        self.assertEqual(new_score.points_awarded, 3)

    def test_process_all_scores_admin_view_handles_errors(self) -> None:
        """Test that the admin view handles errors gracefully."""
        self.client.force_login(self.admin_user)
        
        # Create a user and tip
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
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
        
        # Create outcome without winning option (invalid)
        EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=None,
            winning_generic_option=None,
        )
        
        # Process scores via admin
        url = reverse('admin:predictions_usereventscore_process_all_scores')
        response = self.client.post(url)
        
        # Should redirect back to changelist
        self.assertEqual(response.status_code, 302)
        
        # Should not create any scores
        self.assertEqual(UserEventScore.objects.count(), 0)

    def test_user_event_score_changelist_template_has_buttons(self) -> None:
        """Test that the UserEventScore changelist template includes the processing buttons."""
        self.client.force_login(self.admin_user)
        
        url = reverse('admin:predictions_usereventscore_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that the template contains the processing buttons
        content = response.content.decode('utf-8')
        self.assertIn('Process All Scores', content)
        self.assertIn('Force Recalculate All Scores', content)
        self.assertIn('process-all-scores', content)

    def test_process_all_scores_admin_view_returns_locks(self) -> None:
        """Test that the admin view returns locks to users when processing scores."""
        self.client.force_login(self.admin_user)
        
        # Create a user and tip with lock
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
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
        
        # Create outcome
        EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )
        
        # Process scores via admin
        url = reverse('admin:predictions_usereventscore_process_all_scores')
        response = self.client.post(url)
        
        # Should redirect back to changelist
        self.assertEqual(response.status_code, 302)
        
        # Should create a score
        self.assertEqual(UserEventScore.objects.count(), 1)
        score = UserEventScore.objects.get()
        self.assertEqual(score.user, user)
        self.assertEqual(score.points_awarded, 6)  # 3 points * 2 (lock multiplier)
        self.assertTrue(score.is_lock_bonus)
        
        # Should return the lock to the user (status goes to WAS_LOCKED to preserve bonus points)
        tip.refresh_from_db()
        self.assertFalse(tip.is_locked)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.WAS_LOCKED)
        self.assertIsNotNone(tip.lock_released_at)

    def test_process_all_scores_admin_view_forfeits_locks(self) -> None:
        """Test that the admin view forfeits locks for incorrect predictions."""
        self.client.force_login(self.admin_user)
        
        # Create a user and tip with lock (wrong prediction)
        user = self.user_model.objects.create_user("user", "user@example.com", "password")
        tip = UserTip.objects.create(
            user=user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.celtics_option,  # Wrong choice
            selected_option=self.celtics_option_obj,
            prediction="Boston Celtics",
            is_locked=True,
            lock_status=UserTip.LockStatus.ACTIVE,
        )
        
        # Create outcome (Lakers win)
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.lakers_option,
            winning_generic_option=self.lakers_option_obj,
        )
        
        # Process scores via admin
        url = reverse('admin:predictions_usereventscore_process_all_scores')
        response = self.client.post(url)
        
        # Should redirect back to changelist
        self.assertEqual(response.status_code, 302)
        
        # Should not create any scores (wrong prediction)
        self.assertEqual(UserEventScore.objects.count(), 0)
        
        # Should forfeit the lock
        tip.refresh_from_db()
        self.assertFalse(tip.is_locked)
        self.assertEqual(tip.lock_status, UserTip.LockStatus.FORFEITED)
        self.assertIsNotNone(tip.lock_releases_at)
        self.assertIsNone(tip.lock_released_at)
        
        # Verify the release time is set to 30 days after resolution
        from datetime import timedelta
        expected_release_time = outcome.resolved_at + timedelta(days=30)
        self.assertEqual(tip.lock_releases_at, expected_release_time)
