from datetime import timedelta
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hooptipp.predictions.models import (
    EventOutcome,
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    Season,
    TipType,
    UserEventScore,
    UserTip,
)
from hooptipp.predictions.scoring_service import ScoreEventResult


# TODO: Move these tests to hooptipp.nba.tests once NBA admin is fully migrated
# class NbaPlayerAdminSyncTests(TestCase):
#     These tests are temporarily disabled during NBA module extraction

# class NbaTeamAdminSyncTests(TestCase):
#     These tests are temporarily disabled during NBA module extraction


class EventOutcomeAdminScoreTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password123',
        )
        self.client.force_login(self.user)

        now = timezone.now()
        
        # Create option category and option
        teams_cat = OptionCategory.objects.create(
            slug='test-teams',
            name='Test Teams'
        )
        self.team_option = Option.objects.create(
            category=teams_cat,
            slug='mm',
            name='Metropolis Meteors',
            short_name='MM',
            external_id='99',
            metadata={'city': 'Metropolis', 'conference': 'East', 'division': 'Atlantic'}
        )
        
        self.tip_type = TipType.objects.create(
            name='Daily Picks',
            slug='daily-picks',
            deadline=now + timedelta(days=30),
        )
        self.event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Game Winner',
            description='Pick the winning team',
            points=3,
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(days=1),
        )
        self.option = PredictionOption.objects.create(
            event=self.event,
            label='Metropolis Meteors',
            option=self.team_option,
        )
        self.outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.option,
            winning_generic_option=self.team_option,
        )

        UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.option,
            selected_option=self.team_option,
            prediction='Metropolis Meteors',
        )

        return super().setUp()

    def test_score_outcome_requires_post(self) -> None:
        url = reverse('admin:predictions_eventoutcome_score', args=[self.outcome.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_score_outcome_awards_points_and_redirects(self) -> None:
        url = reverse('admin:predictions_eventoutcome_score', args=[self.outcome.pk])

        response = self.client.post(url, follow=True)

        self.assertEqual(response.status_code, 200)
        scores = UserEventScore.objects.filter(prediction_event=self.event)
        self.assertEqual(scores.count(), 1)
        self.assertEqual(scores.first().points_awarded, self.event.points)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Scored' in message.message for message in messages))

    def test_score_outcome_handles_errors(self) -> None:
        url = reverse('admin:predictions_eventoutcome_score', args=[self.outcome.pk])

        error_message = 'Outcome is missing a winning selection.'
        with mock.patch(
            'hooptipp.predictions.admin.scoring_service.score_event_outcome',
            side_effect=ValueError(error_message),
        ) as mock_score:
            response = self.client.post(url, follow=True)

        mock_score.assert_called_once_with(self.outcome, force=False)
        self.assertEqual(response.status_code, 200)

        self.outcome.refresh_from_db()
        self.assertEqual(self.outcome.score_error, error_message)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any(error_message in message.message for message in messages))

    def test_force_flag_re_scores_event(self) -> None:
        url = reverse('admin:predictions_eventoutcome_score', args=[self.outcome.pk])

        with mock.patch(
            'hooptipp.predictions.admin.scoring_service.score_event_outcome',
            return_value=ScoreEventResult(
                event=self.event,
                outcome=self.outcome,
                awarded_scores=[],
                skipped_tips=0,
            ),
        ) as mock_score:
            response = self.client.post(url, data={'force': '1'}, follow=True)

        mock_score.assert_called_once_with(self.outcome, force=True)
        self.assertEqual(response.status_code, 200)


@override_settings(ALLOWED_HOSTS=['testserver'])
class EventOutcomeAdminTemplateTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='process-events',
        )
        self.client.force_login(self.user)
        super().setUp()

    def _create_event_outcome(self, **extra_fields: object) -> EventOutcome:
        now = timezone.now()
        tip_type = TipType.objects.create(
            name='Test Tip Type',
            slug=f'test-tip-{uuid.uuid4()}',
            deadline=now + timedelta(days=7),
        )
        event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name=f'Event {uuid.uuid4()}',
            opens_at=now - timedelta(days=2),
            deadline=now - timedelta(days=1),
        )
        return EventOutcome.objects.create(
            prediction_event=event,
            **extra_fields,
        )

    def test_change_form_includes_process_event_button(self) -> None:
        outcome = self._create_event_outcome()
        url = reverse('admin:predictions_eventoutcome_change', args=[outcome.pk])

        response = self.client.get(url)

        self.assertContains(response, 'Process event')
        self.assertNotContains(response, 'Re-score event')

    def test_change_form_includes_re_score_button_when_scored(self) -> None:
        outcome = self._create_event_outcome(scored_at=timezone.now())
        url = reverse('admin:predictions_eventoutcome_change', args=[outcome.pk])

        response = self.client.get(url)

        self.assertContains(response, 'Process event')
        self.assertContains(response, 'Re-score event')


class EventSourceAdminTests(TestCase):
    """Tests for EventSourceAdmin to ensure it works without a backing database table."""
    
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password123',
        )
        self.client.force_login(self.user)
        super().setUp()
    
    def test_changelist_view_loads_without_database_error(self) -> None:
        """Test that the EventSource changelist view loads without querying the database."""
        url = reverse('admin:predictions_eventsourcepseudomodel_changelist')
        
        response = self.client.get(url)
        
        # Should return 200 without database errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Event Sources')
    
    def test_changelist_displays_registered_sources(self) -> None:
        """Test that registered event sources are displayed in the changelist."""
        url = reverse('admin:predictions_eventsourcepseudomodel_changelist')
        
        response = self.client.get(url)
        
        # Should contain information about event sources
        # The actual sources depend on what's registered, but the page should render
        self.assertEqual(response.status_code, 200)
        self.assertIn('sources', response.context)
        self.assertIsInstance(response.context['sources'], list)


class SeasonAdminTests(TestCase):
    """Tests for SeasonAdmin to ensure changelist works correctly."""
    
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password123',
        )
        self.client.force_login(self.user)
        super().setUp()
    
    def test_changelist_view_loads_without_error(self) -> None:
        """Test that the Season changelist view loads without errors."""
        from datetime import datetime
        from django.utils import timezone
        
        # Create a test season
        Season.objects.create(
            name='Test Season',
            start_date=timezone.make_aware(datetime(2025, 1, 1, 0, 0, 0)),
            end_date=timezone.make_aware(datetime(2025, 12, 31, 23, 59, 59))
        )
        
        url = reverse('admin:predictions_season_changelist')
        
        response = self.client.get(url)
        
        # Should return 200 without errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Seasons')
        self.assertContains(response, 'Test Season')
    
    def test_changelist_displays_is_active_status(self) -> None:
        """Test that the changelist displays the is_active_display column."""
        from datetime import datetime
        from django.utils import timezone
        
        # Create a test season
        season = Season.objects.create(
            name='Active Season',
            start_date=timezone.make_aware(datetime(2024, 1, 1, 0, 0, 0)),
            end_date=timezone.make_aware(datetime(2026, 12, 31, 23, 59, 59))
        )
        
        url = reverse('admin:predictions_season_changelist')
        
        response = self.client.get(url)
        
        # Should return 200 and contain the season
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Active Season')
        # Should contain the status column (either Active or Inactive)
        self.assertIn('Status', response.content.decode())


class EventOutcomeBatchAddTests(TestCase):
    """Tests for the batch add event outcomes functionality."""
    
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password123',
        )
        self.client.force_login(self.user)
        
        now = timezone.now()
        
        # Create option category and options
        teams_cat = OptionCategory.objects.create(
            slug='test-teams',
            name='Test Teams'
        )
        self.team1 = Option.objects.create(
            category=teams_cat,
            slug='team1',
            name='Team 1',
            short_name='T1'
        )
        self.team2 = Option.objects.create(
            category=teams_cat,
            slug='team2',
            name='Team 2',
            short_name='T2'
        )
        
        self.tip_type = TipType.objects.create(
            name='Test Tip Type',
            slug='test-tip',
            deadline=now + timedelta(days=30),
        )
        
        # Create events - some past deadline, some not
        self.past_event1 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Past Event 1',
            opens_at=now - timedelta(days=3),
            deadline=now - timedelta(days=1),  # Past deadline
        )
        self.past_event2 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Past Event 2',
            opens_at=now - timedelta(days=3),
            deadline=now - timedelta(days=2),  # Past deadline
        )
        self.future_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Future Event',
            opens_at=now - timedelta(days=1),
            deadline=now + timedelta(days=1),  # Future deadline
        )
        
        # Create options for past events
        self.option1a = PredictionOption.objects.create(
            event=self.past_event1,
            label='Team 1',
            option=self.team1,
        )
        self.option1b = PredictionOption.objects.create(
            event=self.past_event1,
            label='Team 2',
            option=self.team2,
        )
        self.option2a = PredictionOption.objects.create(
            event=self.past_event2,
            label='Team 1',
            option=self.team1,
        )
        self.option2b = PredictionOption.objects.create(
            event=self.past_event2,
            label='Team 2',
            option=self.team2,
        )
        
        # Create an outcome for one past event (should not appear in batch add)
        EventOutcome.objects.create(
            prediction_event=self.past_event2,
            winning_option=self.option2a,
            winning_generic_option=self.team1,
            resolved_by=self.user,
        )

    def test_batch_add_view_requires_permission(self) -> None:
        """Test that batch add view requires add permission."""
        # Create a user without permissions
        user = get_user_model().objects.create_user(
            username='regular_user',
            email='user@example.com',
            password='password123',
        )
        self.client.force_login(user)
        
        url = reverse('admin:predictions_eventoutcome_batch_add')
        response = self.client.get(url)
        
        # Django redirects to login or shows 403 depending on configuration
        self.assertIn(response.status_code, [302, 403])

    def test_batch_add_view_shows_only_past_events_without_outcomes(self) -> None:
        """Test that batch add view only shows events past deadline without outcomes."""
        url = reverse('admin:predictions_eventoutcome_batch_add')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Past Event 1')  # Past deadline, no outcome
        self.assertNotContains(response, 'Past Event 2')  # Past deadline, but has outcome
        self.assertNotContains(response, 'Future Event')  # Future deadline

    def test_batch_add_view_shows_event_options(self) -> None:
        """Test that batch add view shows available options for each event."""
        url = reverse('admin:predictions_eventoutcome_batch_add')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Team 1')
        self.assertContains(response, 'Team 2')
        self.assertContains(response, f'winning_option_{self.past_event1.id}')

    def test_batch_add_view_no_events_message(self) -> None:
        """Test that batch add view shows appropriate message when no events need outcomes."""
        # Create outcome for the remaining past event
        EventOutcome.objects.create(
            prediction_event=self.past_event1,
            winning_option=self.option1a,
            winning_generic_option=self.team1,
            resolved_by=self.user,
        )
        
        url = reverse('admin:predictions_eventoutcome_batch_add')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No events found that need outcomes')

    def test_batch_add_submission_creates_outcomes(self) -> None:
        """Test that batch add submission creates outcomes for selected events."""
        url = reverse('admin:predictions_eventoutcome_batch_add')
        
        data = {
            f'winning_option_{self.past_event1.id}': self.option1a.id,
        }
        
        response = self.client.post(url, data, follow=True)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that outcome was created
        outcome = EventOutcome.objects.get(prediction_event=self.past_event1)
        self.assertEqual(outcome.winning_option, self.option1a)
        self.assertEqual(outcome.winning_generic_option, self.team1)
        self.assertEqual(outcome.resolved_by, self.user)
        
        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Successfully created 1 event outcomes' in message.message for message in messages))

    def test_batch_add_submission_ignores_empty_selections(self) -> None:
        """Test that batch add submission ignores events with no selection."""
        url = reverse('admin:predictions_eventoutcome_batch_add')
        
        # Submit with no selections
        data = {}
        
        response = self.client.post(url, data, follow=True)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that no outcomes were created
        self.assertEqual(EventOutcome.objects.filter(prediction_event=self.past_event1).count(), 0)
        
        # Check info message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('No outcomes were created' in message.message for message in messages))

    def test_batch_add_submission_handles_invalid_option(self) -> None:
        """Test that batch add submission handles invalid option selections."""
        url = reverse('admin:predictions_eventoutcome_batch_add')
        
        # Submit with invalid option ID
        data = {
            f'winning_option_{self.past_event1.id}': 99999,  # Non-existent option
        }
        
        response = self.client.post(url, data, follow=True)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that no outcomes were created
        self.assertEqual(EventOutcome.objects.filter(prediction_event=self.past_event1).count(), 0)
        
        # Check error message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Invalid option selected' in message.message for message in messages))

    def test_batch_add_submission_creates_multiple_outcomes(self) -> None:
        """Test that batch add submission can create multiple outcomes at once."""
        # Create another past event without outcome
        past_event3 = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Past Event 3',
            opens_at=timezone.now() - timedelta(days=3),
            deadline=timezone.now() - timedelta(days=1),
        )
        option3a = PredictionOption.objects.create(
            event=past_event3,
            label='Team 1',
            option=self.team1,
        )
        
        url = reverse('admin:predictions_eventoutcome_batch_add')
        
        data = {
            f'winning_option_{self.past_event1.id}': self.option1a.id,
            f'winning_option_{past_event3.id}': option3a.id,
        }
        
        response = self.client.post(url, data, follow=True)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that both outcomes were created
        self.assertEqual(EventOutcome.objects.filter(prediction_event=self.past_event1).count(), 1)
        self.assertEqual(EventOutcome.objects.filter(prediction_event=past_event3).count(), 1)
        
        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Successfully created 2 event outcomes' in message.message for message in messages))

    def test_batch_add_redirects_to_changelist(self) -> None:
        """Test that batch add submission redirects to the changelist."""
        url = reverse('admin:predictions_eventoutcome_batch_add')
        
        data = {
            f'winning_option_{self.past_event1.id}': self.option1a.id,
        }
        
        response = self.client.post(url, data)
        
        self.assertRedirects(response, reverse('admin:predictions_eventoutcome_changelist'))
