from datetime import timedelta
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hooptipp.predictions import services
from hooptipp.predictions.models import (
    EventOutcome,
    NbaTeam,
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
    UserEventScore,
    UserTip,
)
from hooptipp.predictions.scoring_service import ScoreEventResult


class NbaPlayerAdminSyncTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password123',
        )
        self.client.force_login(self.user)
        return super().setUp()

    def test_sync_players_requires_post(self) -> None:
        url = reverse('admin:predictions_nbaplayer_sync')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_sync_players_triggers_service_and_shows_message(self) -> None:
        url = reverse('admin:predictions_nbaplayer_sync')
        sync_result = services.PlayerSyncResult(created=1, updated=2, removed=3)

        with mock.patch('hooptipp.predictions.admin.services.sync_active_players', return_value=sync_result) as mock_sync:
            response = self.client.post(url, follow=True)

        mock_sync.assert_called_once_with()
        self.assertEqual(response.status_code, 200)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Player data updated' in message.message for message in messages))


class NbaTeamAdminSyncTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password123',
        )
        self.client.force_login(self.user)
        return super().setUp()

    def test_sync_teams_requires_post(self) -> None:
        url = reverse('admin:predictions_nbateam_sync')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_sync_teams_triggers_service_and_shows_message(self) -> None:
        url = reverse('admin:predictions_nbateam_sync')
        sync_result = services.TeamSyncResult(created=2, updated=1, removed=0)

        with mock.patch('hooptipp.predictions.admin.services.sync_teams', return_value=sync_result) as mock_sync:
            response = self.client.post(url, follow=True)

        mock_sync.assert_called_once_with()
        self.assertEqual(response.status_code, 200)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Team data updated' in message.message for message in messages))


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
        self.team = NbaTeam.objects.create(name='Metropolis Meteors', abbreviation='MM')
        self.team_option = Option.objects.create(
            category=teams_cat,
            slug='mm',
            name='Metropolis Meteors',
            short_name='MM',
            metadata={'nba_team_id': self.team.id}
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
