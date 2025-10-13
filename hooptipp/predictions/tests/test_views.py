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
            return_value=(self.tip_type, [self.game]),
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
