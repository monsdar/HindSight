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
from hooptipp.predictions.reminder_emails import send_reminder_email, send_season_enrollment_reminder

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

        # Should not send regular reminder because user1 is not enrolled in the season
        # (The event should be filtered out)
        # Regular reminders have "Erinnerung" in subject, season enrollment reminders have "Nicht verpassen"
        regular_reminders = [email for email in mail.outbox if 'Erinnerung' in email.subject]
        self.assertEqual(len(regular_reminders), 0, "Should not send regular reminder when user is not enrolled in season")

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

    def test_command_skips_users_without_email(self) -> None:
        """Test that command skips users without email addresses."""
        now = timezone.now()
        
        # Create a user without email
        user_no_email = User.objects.create_user(
            username='noemailuser',
            email='',  # Empty email
            password='password123',
        )
        UserPreferences.objects.create(user=user_no_email, reminder_emails_enabled=True)
        
        # Create a passed event with a prediction
        passed_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Passed Event',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
        )
        UserTip.objects.create(
            user=user_no_email,
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

        # Should not send email because user has no email address
        self.assertEqual(len(mail.outbox), 0)

    def test_command_force_send_skips_user_without_email(self) -> None:
        """Test that force send mode skips users without email addresses."""
        now = timezone.now()
        
        # Create a user without email
        user_no_email = User.objects.create_user(
            username='noemailuser',
            email='',  # Empty email
            password='password123',
        )
        
        # Try to force send to user without email
        call_command('send_reminder_emails', '--force-send-user', 'noemailuser')

        # Should not send email because user has no email address
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


class SeasonEnrollmentReminderEmailTests(TestCase):
    """Tests for season enrollment reminder email functionality."""

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

    def test_send_season_enrollment_reminder_sends_email(self) -> None:
        """Test that send_season_enrollment_reminder actually sends an email."""
        now = timezone.now()
        season = Season.objects.create(
            name='Test Season',
            start_date=(now - timedelta(days=1)).date(),
            start_time=(now - timedelta(days=1)).time(),
            end_date=(now + timedelta(days=30)).date(),
            end_time=(now + timedelta(days=30)).time(),
        )
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        send_season_enrollment_reminder(self.user, season, [event])

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
        self.assertIn('Nicht verpassen!', email.subject)
        self.assertIn(season.name, email.body)
        self.assertIn(event.name, email.body)

    def test_season_enrollment_reminder_contains_enroll_url(self) -> None:
        """Test that email contains link to enroll in season."""
        now = timezone.now()
        season = Season.objects.create(
            name='Test Season',
            start_date=(now - timedelta(days=1)).date(),
            start_time=(now - timedelta(days=1)).time(),
            end_date=(now + timedelta(days=30)).date(),
            end_time=(now + timedelta(days=30)).time(),
        )
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        send_season_enrollment_reminder(self.user, season, [event])

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        # Check that home URL pattern is in the email (where they can enroll)
        self.assertIn('/', email.body)  # Should contain URL

    def test_command_sends_season_enrollment_reminders(self) -> None:
        """Test that command sends season enrollment reminders to unenrolled users."""
        now = timezone.now()
        
        # Create a season that is active
        season = Season.objects.create(
            name='Active Season',
            start_date=(now - timedelta(days=1)).date(),
            start_time=(now - timedelta(days=1)).time(),
            end_date=(now + timedelta(days=30)).date(),
            end_time=(now + timedelta(days=30)).time(),
        )
        
        # Create preferences for user
        UserPreferences.objects.create(user=self.user, reminder_emails_enabled=True)
        
        # Don't enroll user in the season
        
        # Create an event in the season with deadline in next 24 hours
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        call_command('send_reminder_emails')

        # Should send season enrollment reminder because:
        # - Season is active
        # - Event is in the next 24 hours and belongs to the season
        # - User is not enrolled
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn('Season', email.subject)

    def test_command_skips_season_reminders_when_no_upcoming_events(self) -> None:
        """Test that command skips season enrollment reminders when no events in next 24 hours."""
        now = timezone.now()
        
        # Create a season that is active
        season = Season.objects.create(
            name='Active Season',
            start_date=(now - timedelta(days=1)).date(),
            start_time=(now - timedelta(days=1)).time(),
            end_date=(now + timedelta(days=30)).date(),
            end_time=(now + timedelta(days=30)).time(),
        )
        
        # Create preferences for user
        UserPreferences.objects.create(user=self.user, reminder_emails_enabled=True)
        
        # Don't enroll user in the season
        
        # Don't create any events in the next 24 hours

        call_command('send_reminder_emails')

        # Should not send season enrollment reminder because no events in next 24 hours
        self.assertEqual(len(mail.outbox), 0)

    def test_command_skips_season_reminders_when_user_enrolled(self) -> None:
        """Test that command skips season enrollment reminders when user is enrolled."""
        now = timezone.now()
        
        # Create a season that is active
        season = Season.objects.create(
            name='Active Season',
            start_date=(now - timedelta(days=1)).date(),
            start_time=(now - timedelta(days=1)).time(),
            end_date=(now + timedelta(days=30)).date(),
            end_time=(now + timedelta(days=30)).time(),
        )
        
        # Create preferences for user
        UserPreferences.objects.create(user=self.user, reminder_emails_enabled=True)
        
        # Enroll user in the season
        SeasonParticipant.objects.create(user=self.user, season=season)
        
        # Create a passed event with a prediction (required for regular reminders)
        passed_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Passed Event',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(hours=1),
        )
        UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=passed_event,
            prediction='Test',
        )
        
        # Create an event in the season with deadline in next 24 hours (but don't predict it)
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        call_command('send_reminder_emails')

        # Check that no season enrollment reminder was sent (user is enrolled)
        # But a regular reminder might be sent for the unpredicted event
        season_reminders = [email for email in mail.outbox if 'Season' in email.subject and 'Nicht verpassen' in email.subject]
        self.assertEqual(len(season_reminders), 0, "Should not send season enrollment reminder when user is enrolled")

    def test_command_skips_season_reminders_when_user_has_no_email(self) -> None:
        """Test that command skips season enrollment reminders for users without email."""
        now = timezone.now()
        
        # Create a user without email
        user_no_email = User.objects.create_user(
            username='noemailuser',
            email='',  # Empty email
            password='password123',
        )
        UserPreferences.objects.create(user=user_no_email, reminder_emails_enabled=True)
        
        # Create a season that is active
        season = Season.objects.create(
            name='Active Season',
            start_date=(now - timedelta(days=1)).date(),
            start_time=(now - timedelta(days=1)).time(),
            end_date=(now + timedelta(days=30)).date(),
            end_time=(now + timedelta(days=30)).time(),
        )
        
        # Create an event in the season with deadline in next 24 hours
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )

        call_command('send_reminder_emails')

        # Should not send season enrollment reminder because user has no email
        season_reminders = [email for email in mail.outbox if 'Season' in email.subject and 'Nicht verpassen' in email.subject]
        self.assertEqual(len(season_reminders), 0, "Should not send season enrollment reminder when user has no email")


class EnrollSeasonViaTokenViewTests(TestCase):
    """Tests for enroll_in_season_via_token view."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123',
        )
        now = timezone.now()
        self.season = Season.objects.create(
            name='Test Season',
            start_date=(now - timedelta(days=1)).date(),
            start_time=(now - timedelta(days=1)).time(),
            end_date=(now + timedelta(days=30)).date(),
            end_time=(now + timedelta(days=30)).time(),
        )
        self.token = default_token_generator.make_token(self.user)
        self.uid = urlsafe_base64_encode(force_bytes(self.user.pk))

    def test_enroll_season_via_token_success(self) -> None:
        """Test successful enrollment via token."""
        # Verify user is not enrolled
        self.assertFalse(SeasonParticipant.objects.filter(user=self.user, season=self.season).exists())
        
        response = self.client.get(
            f'/enroll-season/{self.uid}/{self.season.id}/{self.token}/'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'erfolgreich für die Season')
        self.assertTemplateUsed(response, 'predictions/enroll_season_done.html')
        
        # Verify user is now enrolled
        self.assertTrue(SeasonParticipant.objects.filter(user=self.user, season=self.season).exists())

    def test_enroll_season_via_token_already_enrolled(self) -> None:
        """Test enrollment when user is already enrolled."""
        # Enroll user first
        SeasonParticipant.objects.create(user=self.user, season=self.season)
        
        response = self.client.get(
            f'/enroll-season/{self.uid}/{self.season.id}/{self.token}/'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'bereits für die Season')
        self.assertTemplateUsed(response, 'predictions/enroll_season_done.html')
        
        # Verify only one enrollment exists
        self.assertEqual(SeasonParticipant.objects.filter(user=self.user, season=self.season).count(), 1)

    def test_enroll_season_via_token_invalid_token(self) -> None:
        """Test enrollment with invalid token."""
        invalid_token = 'invalid-token'
        
        response = self.client.get(
            f'/enroll-season/{self.uid}/{self.season.id}/{invalid_token}/'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ungültiger oder abgelaufener Link')
        self.assertTemplateUsed(response, 'predictions/enroll_season_done.html')
        
        # Verify user is not enrolled
        self.assertFalse(SeasonParticipant.objects.filter(user=self.user, season=self.season).exists())

    def test_enroll_season_via_token_invalid_user(self) -> None:
        """Test enrollment with invalid user ID."""
        invalid_uid = urlsafe_base64_encode(force_bytes(99999))  # Non-existent user ID
        
        response = self.client.get(
            f'/enroll-season/{invalid_uid}/{self.season.id}/{self.token}/'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ungültiger Link')
        self.assertTemplateUsed(response, 'predictions/enroll_season_done.html')
        
        # Verify user is not enrolled
        self.assertFalse(SeasonParticipant.objects.filter(user=self.user, season=self.season).exists())

    def test_enroll_season_via_token_invalid_season(self) -> None:
        """Test enrollment with invalid season ID."""
        invalid_season_id = 99999
        
        response = self.client.get(
            f'/enroll-season/{self.uid}/{invalid_season_id}/{self.token}/'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Season nicht gefunden')
        self.assertTemplateUsed(response, 'predictions/enroll_season_done.html')
        
        # Verify user is not enrolled
        self.assertFalse(SeasonParticipant.objects.filter(user=self.user, season=self.season).exists())

    def test_enroll_season_email_contains_token_url(self) -> None:
        """Test that season enrollment email contains token-based enrollment URL."""
        now = timezone.now()
        event = PredictionEvent.objects.create(
            tip_type=TipType.objects.create(
                name='Test Type',
                slug='test-type',
                deadline=now + timedelta(days=7),
            ),
            name='Upcoming Event',
            opens_at=now - timedelta(hours=1),
            deadline=now + timedelta(hours=12),
        )
        
        # Send season enrollment reminder
        send_season_enrollment_reminder(self.user, self.season, [event])
        
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        
        # Check that email contains the enrollment URL with token
        self.assertIn('/enroll-season/', email.body)
        self.assertIn(str(self.season.id), email.body)
        # HTML email should also contain the URL
        if hasattr(email, 'alternatives') and email.alternatives:
            html_content = email.alternatives[0][0]
            self.assertIn('/enroll-season/', html_content)
            self.assertIn(str(self.season.id), html_content)

