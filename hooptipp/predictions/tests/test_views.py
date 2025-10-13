from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hooptipp.predictions.models import ScheduledGame, TipType, UserTip


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
        self.game = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id='GAME123',
            game_date=timezone.now(),
            home_team='Los Angeles Lakers',
            home_team_tricode='LAL',
            away_team='Boston Celtics',
            away_team_tricode='BOS',
            venue='Crypto.com Arena',
        )
        UserTip.objects.create(
            user=self.alice,
            tip_type=self.tip_type,
            scheduled_game=self.game,
            prediction='BOS',
        )
        UserTip.objects.create(
            user=self.bob,
            tip_type=self.tip_type,
            scheduled_game=self.game,
            prediction='LAL',
        )
        super().setUp()

    def test_home_view_exposes_game_tip_users(self) -> None:
        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.game], self.game.game_date.date()),
        ):
            response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('game_tip_users', response.context)

        game_tip_users = response.context['game_tip_users']
        self.assertIn(self.game.id, game_tip_users)
        usernames = [user.username for user in game_tip_users[self.game.id]]
        self.assertEqual(usernames, ['alice', 'bob'])

        self.assertContains(response, 'title="alice"')
        self.assertContains(response, 'title="bob"')

    def test_active_user_tip_renders_last_updated_timestamp(self) -> None:
        session = self.client.session
        session['active_user_id'] = self.alice.id
        session.save()

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.game], self.game.game_date.date()),
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

        with mock.patch(
            'hooptipp.predictions.views.sync_weekly_games',
            return_value=(self.tip_type, [self.game, additional], self.game.game_date.date()),
        ):
            response = self.client.get(reverse('predictions:home'))

        self.assertEqual(response.status_code, 200)
        weekday_slots = response.context['weekday_slots']
        self.assertEqual(len(weekday_slots), 7)
        first_day_games = weekday_slots[0]['games']
        second_day_games = weekday_slots[1]['games']
        self.assertEqual([game.id for game in first_day_games], [self.game.id])
        self.assertEqual([game.id for game in second_day_games], [additional.id])
