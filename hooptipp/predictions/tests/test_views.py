from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hooptipp.predictions.models import (
    NbaTeam,
    PredictionEvent,
    PredictionOption,
    ScheduledGame,
    TipType,
    UserPreferences,
    UserTip,
)


class HomeViewTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.alice = user_model.objects.create_user(
            username='alice',
            password='password123',
        )
        self.bob = user_model.objects.create_user(
            username='bob',
            password='password123',
        )
        self.tip_type = TipType.objects.create(
            name='Weekly games',
            slug='weekly-games',
            description='Featured matchups for the upcoming week',
            deadline=timezone.now(),
        )
        self.home_team = NbaTeam.objects.create(
            name='Los Angeles Lakers',
            abbreviation='LAL',
        )
        self.away_team = NbaTeam.objects.create(
            name='Boston Celtics',
            abbreviation='BOS',
        )
        game_time = timezone.now() + timedelta(hours=1)
        self.game = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id='GAME123',
            game_date=game_time,
            home_team='Los Angeles Lakers',
            home_team_tricode='LAL',
            away_team='Boston Celtics',
            away_team_tricode='BOS',
            venue='Crypto.com Arena',
        )
        self.event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='BOS @ LAL',
            description='Boston Celtics at Los Angeles Lakers',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            opens_at=timezone.now() - timedelta(days=1),
            deadline=game_time,
            reveal_at=timezone.now() - timedelta(days=1),
            is_active=True,
            scheduled_game=self.game,
            sort_order=1,
        )
        self.away_option = PredictionOption.objects.create(
            event=self.event,
            label='Boston Celtics',
            team=self.away_team,
            sort_order=1,
        )
        self.home_option = PredictionOption.objects.create(
            event=self.event,
            label='Los Angeles Lakers',
            team=self.home_team,
            sort_order=2,
        )
        UserTip.objects.create(
            user=self.alice,
            tip_type=self.tip_type,
            scheduled_game=self.game,
            prediction_event=self.event,
            prediction_option=self.away_option,
            selected_team=self.away_team,
            prediction='BOS',
        )
        UserTip.objects.create(
            user=self.bob,
            tip_type=self.tip_type,
            scheduled_game=self.game,
            prediction_event=self.event,
            prediction_option=self.home_option,
            selected_team=self.home_team,
            prediction='LAL',
        )
        super().setUp()

    def test_home_view_exposes_event_tip_users(self) -> None:
        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ):
            response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('event_tip_users', response.context)

        event_tip_users = response.context['event_tip_users']
        self.assertIn(self.event.id, event_tip_users)
        usernames = [user.username for user in event_tip_users[self.event.id]]
        self.assertEqual(usernames, ['alice', 'bob'])

        self.assertContains(response, 'title="alice"')
        self.assertContains(response, 'title="bob"')

    def test_active_user_tip_renders_last_updated_timestamp(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ):
            response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Last updated:')

    def test_weekday_slots_group_games_by_date(self) -> None:
        additional = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id='GAME456',
            game_date=self.game.game_date + timedelta(days=1),
            home_team='Chicago Bulls',
            home_team_tricode='CHI',
            away_team='Miami Heat',
            away_team_tricode='MIA',
            venue='United Center',
            is_manual=True,
        )
        away_team = NbaTeam.objects.create(name='Miami Heat', abbreviation='MIA')
        home_team = NbaTeam.objects.create(name='Chicago Bulls', abbreviation='CHI')
        additional_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='MIA @ CHI',
            description='Miami Heat at Chicago Bulls',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            opens_at=timezone.now() - timedelta(days=1),
            deadline=additional.game_date,
            reveal_at=timezone.now() - timedelta(days=1),
            is_active=True,
            scheduled_game=additional,
            sort_order=2,
        )
        PredictionOption.objects.create(
            event=additional_event,
            label='Miami Heat',
            team=away_team,
            sort_order=1,
        )
        PredictionOption.objects.create(
            event=additional_event,
            label='Chicago Bulls',
            team=home_team,
            sort_order=2,
        )

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event, additional_event], self.game.game_date.date()),
        ):
            response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        weekday_slots = response.context['weekday_slots']
        self.assertEqual(len(weekday_slots), 7)
        first_day_events = weekday_slots[0]['games']
        second_day_events = weekday_slots[1]['games']
        self.assertEqual([event.id for event in first_day_events], [self.event.id])
        self.assertEqual([event.id for event in second_day_events], [additional_event.id])

    def test_update_preferences_updates_record(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ), mock.patch(
            'hooptipp.predictions.forms.get_team_choices',
            return_value=[('42', 'Golden State Warriors')],
        ), mock.patch(
            'hooptipp.predictions.forms.get_player_choices',
            return_value=[('8', 'Stephen Curry')],
        ), mock.patch(
            'hooptipp.predictions.services.get_team_choices',
            return_value=[('42', 'Golden State Warriors')],
        ), mock.patch(
            'hooptipp.predictions.services.get_player_choices',
            return_value=[('8', 'Stephen Curry')],
        ):
            response = self.client.post(
                reverse('predictions:home'),
                {
                    'update_preferences': '1',
                    'nickname': 'Splash',
                    'favorite_team_id': '42',
                    'favorite_player_id': '8',
                    'theme_primary_color': '#0a7abf',
                    'theme_secondary_color': '#ffffff',
                },
            )

        self.assertEqual(response.status_code, 302)
        preferences = UserPreferences.objects.get(user=self.alice)
        self.assertEqual(preferences.nickname, 'Splash')
        self.assertEqual(preferences.favorite_team_id, 42)
        self.assertEqual(preferences.favorite_player_id, 8)
        self.assertEqual(preferences.theme_primary_color, '#0a7abf')
        self.assertEqual(preferences.theme_secondary_color, '#ffffff')

    def test_update_preferences_validation_errors_return_to_page(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.event], self.game.game_date.date()),
        ), mock.patch(
            'hooptipp.predictions.forms.get_team_choices',
            return_value=[('42', 'Golden State Warriors')],
        ), mock.patch(
            'hooptipp.predictions.forms.get_player_choices',
            return_value=[('8', 'Stephen Curry')],
        ), mock.patch(
            'hooptipp.predictions.services.get_team_choices',
            return_value=[('42', 'Golden State Warriors')],
        ), mock.patch(
            'hooptipp.predictions.services.get_player_choices',
            return_value=[('8', 'Stephen Curry')],
        ):
            response = self.client.post(
                reverse('predictions:home'),
                {
                    'update_preferences': '1',
                    'nickname': 'Splash',
                    'favorite_team_id': '42',
                    'favorite_player_id': '8',
                    'theme_primary_color': '0a7abf',
                    'theme_secondary_color': '#fffff',
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('preferences_form', response.context)
        form = response.context['preferences_form']
        self.assertTrue(form.errors)
        self.assertIn('theme_primary_color', form.errors)
        self.assertIn('theme_secondary_color', form.errors)
