"""
Tests for reminder email functionality.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from hooptipp.predictions.models import (
    PredictionEvent,
    Season,
    SeasonParticipant,
    TipType,
    UserPreferences,
    UserTip,
)
from hooptipp.predictions.reminder_emails import send_reminder_email

User = get_user_model()


class ReminderEmailUtilityTests(TestCase):
    """Tests for reminder email utility functions."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123',
        )
        self.tip_type = TipType.objects.create(
            name='Test Type',
            slug='test-type',
            deadline=timezone.now() + timedelta(days=7),
        )

    def test_send_reminder_email_sends_email(self) -> None:
        """Test that send_reminder_email actually sends an email."""
        now = timezone.now()
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        send_reminder_email(self.user, [event])

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
        self.assertIn('Erinnerung: Offene Tipps', email.subject)
        self.assertIn(event.name, email.body)

    def test_send_reminder_email_contains_event_list(self) -> None:
        """Test that email contains list of events."""
        now = timezone.now()
        event1 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event 1',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=10),
        )
        event2 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Event 2',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=20),
        )

        send_reminder_email(self.user, [event1, event2])

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn(event1.name, email.body)
        self.assertIn(event2.name, email.body)

    def test_send_reminder_email_contains_disable_url(self) -> None:
        """Test that email contains link to disable reminders."""
        now = timezone.now()
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        send_reminder_email(self.user, [event])

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        # Check that disable URL pattern is in the email
        self.assertIn('disable-reminders', email.body)


class ReminderEmailManagementCommandTests(TestCase):
    """Tests for send_reminder_emails management command."""

    def setUp(self) -> None:
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='password123',
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='password123',
        )
        self.user3 = User.objects.create_user(
            username='user3',
            email='user3@example.com',
            password='password123',
            is_active=False,  # Inactive user
        )
        
        # Create preferences
        UserPreferences.objects.create(user=self.user1, reminder_emails_enabled=True)
        UserPreferences.objects.create(user=self.user2, reminder_emails_enabled=False)  # Disabled
        UserPreferences.objects.create(user=self.user3, reminder_emails_enabled=True)
        
        self.tip_type = TipType.objects.create(
            name='Test Type',
            slug='test-type',
            deadline=timezone.now() + timedelta(days=7),
        )

    def test_command_sends_emails_to_eligible_users(self) -> None:
        """Test that command sends emails to eligible users."""
        now = timezone.now()
        
        # Create a passed event with a prediction for user1
        passed_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Passed Event',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
        )
        UserTip.objects.create(
            user=self.user1,
            tip_type=self.tip_type,
            prediction_event=passed_event,
            prediction='Test',
        )
        
        # Create an upcoming event without prediction
        upcoming_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        call_command('send_reminder_emails')

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user1.email])

    def test_command_skips_users_without_recent_predictions(self) -> None:
        """Test that command skips users who haven't predicted recently passed events."""
        now = timezone.now()
        
        # Create a passed event but user1 hasn't predicted it
        passed_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Passed Event',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
        )
        
        # Create an upcoming event
        upcoming_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        call_command('send_reminder_emails')

        # Should not send email because user1 hasn't predicted the passed event
        self.assertEqual(len(mail.outbox), 0)

    def test_command_skips_users_with_disabled_reminders(self) -> None:
        """Test that command skips users with disabled reminders."""
        now = timezone.now()
        
        # Create a passed event with a prediction for user2
        passed_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Passed Event',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
        )
        UserTip.objects.create(
            user=self.user2,
            tip_type=self.tip_type,
            prediction_event=passed_event,
            prediction='Test',
        )
        
        # Create an upcoming event
        upcoming_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        call_command('send_reminder_emails')

        # Should not send email because user2 has reminders disabled
        self.assertEqual(len(mail.outbox), 0)

    def test_command_skips_inactive_users(self) -> None:
        """Test that command skips inactive users."""
        now = timezone.now()
        
        # Create a passed event with a prediction for user3 (inactive)
        passed_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Passed Event',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
        )
        UserTip.objects.create(
            user=self.user3,
            tip_type=self.tip_type,
            prediction_event=passed_event,
            prediction='Test',
        )
        
        # Create an upcoming event
        upcoming_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        call_command('send_reminder_emails')

        # Should not send email because user3 is inactive
        self.assertEqual(len(mail.outbox), 0)

    def test_command_filters_by_season_enrollment(self) -> None:
        """Test that command filters events by season enrollment."""
        now = timezone.now()
        
        # Create an active season
        season = Season.objects.create(
            name='Test Season',
            start_date=(now - timedelta(days=1)).date(),
            start_time=(now - timedelta(days=1)).time(),
            end_date=(now + timedelta(days=30)).date(),
            end_time=(now + timedelta(days=30)).time(),
        )
        
        # Enroll user1 in the season
        SeasonParticipant.objects.create(user=self.user1, season=season)
        
        # Create a passed event with a prediction
        passed_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Passed Event',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
        )
        UserTip.objects.create(
            user=self.user1,
            tip_type=self.tip_type,
            prediction_event=passed_event,
            prediction='Test',
        )
        
        # Create an upcoming event within the season timeframe
        upcoming_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        call_command('send_reminder_emails')

        # Should send email because user1 is enrolled
        self.assertEqual(len(mail.outbox), 1)

    def test_command_excludes_events_when_not_enrolled(self) -> None:
        """Test that command excludes events from active season when user is not enrolled."""
        now = timezone.now()
        
        # Create an active season
        season = Season.objects.create(
            name='Test Season',
            start_date=(now - timedelta(days=1)).date(),
            start_time=(now - timedelta(days=1)).time(),
            end_date=(now + timedelta(days=30)).date(),
            end_time=(now + timedelta(days=30)).time(),
        )
        
        # Don't enroll user1 in the season
        
        # Create a passed event with a prediction
        passed_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Passed Event',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
        )
        UserTip.objects.create(
            user=self.user1,
            tip_type=self.tip_type,
            prediction_event=passed_event,
            prediction='Test',
        )
        
        # Create an upcoming event within the season timeframe
        upcoming_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        call_command('send_reminder_emails')

        # Should not send email because user1 is not enrolled in the season
        self.assertEqual(len(mail.outbox), 0)

    def test_command_includes_events_without_season(self) -> None:
        """Test that command includes events that don't belong to any season."""
        now = timezone.now()
        
        # Create an active season that starts later
        season = Season.objects.create(
            name='Test Season',
            start_date=(now + timedelta(days=2)).date(),
            start_time=(now + timedelta(days=2)).time(),
            end_date=(now + timedelta(days=30)).date(),
            end_time=(now + timedelta(days=30)).time(),
        )
        
        # Don't enroll user1 in the season
        
        # Create a passed event with a prediction
        passed_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Passed Event',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
        )
        UserTip.objects.create(
            user=self.user1,
            tip_type=self.tip_type,
            prediction_event=passed_event,
            prediction='Test',
        )
        
        # Create an upcoming event before season starts (doesn't belong to season)
        upcoming_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),  # Within next 24 hours but before season starts
        )

        call_command('send_reminder_emails')

        # Should send email because event doesn't belong to any season
        self.assertEqual(len(mail.outbox), 1)

    def test_command_dry_run_mode(self) -> None:
        """Test that dry-run mode shows what would be sent without actually sending."""
        now = timezone.now()
        
        # Create a passed event with a prediction
        passed_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Passed Event',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
        )
        UserTip.objects.create(
            user=self.user1,
            tip_type=self.tip_type,
            prediction_event=passed_event,
            prediction='Test',
        )
        
        # Create an upcoming event
        upcoming_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        call_command('send_reminder_emails', '--dry-run')

        # Should not send any emails in dry-run mode
        self.assertEqual(len(mail.outbox), 0)


class DisableRemindersViewTests(TestCase):
    """Tests for disable reminder emails view."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123',
        )
        self.preferences = UserPreferences.objects.create(
            user=self.user,
            reminder_emails_enabled=True,
        )

    def test_disable_reminders_updates_preferences(self) -> None:
        """Test that disable_reminders view updates preferences correctly."""
        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        
        response = self.client.get(f'/disable-reminders/{uid}/{token}/')
        
        self.assertEqual(response.status_code, 200)
        self.preferences.refresh_from_db()
        self.assertFalse(self.preferences.reminder_emails_enabled)

    def test_disable_reminders_validates_token(self) -> None:
        """Test that disable_reminders view validates token."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        invalid_token = 'invalid-token'
        
        response = self.client.get(f'/disable-reminders/{uid}/{invalid_token}/')
        
        self.assertEqual(response.status_code, 200)
        self.preferences.refresh_from_db()
        # Should still be enabled because token was invalid
        self.assertTrue(self.preferences.reminder_emails_enabled)
        # Should show error message
        self.assertContains(response, 'Ungültiger')

    def test_disable_reminders_invalid_user_id(self) -> None:
        """Test that disable_reminders view handles invalid user ID."""
        invalid_uid = 'invalid-uid'
        token = default_token_generator.make_token(self.user)
        
        response = self.client.get(f'/disable-reminders/{invalid_uid}/{token}/')
        
        self.assertEqual(response.status_code, 200)
        self.preferences.refresh_from_db()
        # Should still be enabled because user ID was invalid
        self.assertTrue(self.preferences.reminder_emails_enabled)
        # Should show error message
        self.assertContains(response, 'Ungültiger')


class UserPreferencesReminderEmailTests(TestCase):
    """Tests for UserPreferences reminder_emails_enabled field."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123',
        )

    def test_reminder_emails_enabled_defaults_to_true(self) -> None:
        """Test that reminder_emails_enabled defaults to True."""
        preferences = UserPreferences.objects.create(user=self.user)
        self.assertTrue(preferences.reminder_emails_enabled)

    def test_reminder_emails_enabled_can_be_set_to_false(self) -> None:
        """Test that reminder_emails_enabled can be set to False."""
        preferences = UserPreferences.objects.create(
            user=self.user,
            reminder_emails_enabled=False,
        )
        self.assertFalse(preferences.reminder_emails_enabled)
        
        preferences.reminder_emails_enabled = False
        preferences.save()
        preferences.refresh_from_db()
        self.assertFalse(preferences.reminder_emails_enabled)

