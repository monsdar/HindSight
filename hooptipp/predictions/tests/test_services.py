import os
from datetime import datetime, timezone as dt_timezone
from unittest import TestCase, mock

from balldontlie import exceptions

from hooptipp.predictions import services


class FetchUpcomingWeekGamesTests(TestCase):
    def setUp(self) -> None:
        os.environ.pop('BALLDONTLIE_API_TOKEN', None)
        return super().setUp()

    def test_fetch_upcoming_week_games_parses_payload(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'secret-token'
        fake_now = datetime(2024, 1, 10, 12, 0, tzinfo=dt_timezone.utc)

        scheduled_game = mock.Mock()
        scheduled_game.id = 42
        scheduled_game.status = 'Scheduled'
        scheduled_game.date = '2024-01-12T00:00:00.000Z'
        scheduled_game.home_team = mock.Mock(full_name='Los Angeles Lakers', abbreviation='LAL')
        scheduled_game.visitor_team = mock.Mock(full_name='Boston Celtics', abbreviation='BOS')
        scheduled_game.arena = 'Crypto.com Arena'

        completed_game = mock.Mock()
        completed_game.status = 'Final'
        completed_game.date = '2024-01-12T00:00:00.000Z'

        response = mock.Mock()
        response.data = [scheduled_game, completed_game]

        with mock.patch.object(services.timezone, 'now', return_value=fake_now):
            with mock.patch.object(services, 'BalldontlieAPI') as mock_api:
                mock_client = mock.Mock()
                mock_games_api = mock.Mock()
                mock_client.nba = mock.Mock()
                mock_client.nba.games = mock_games_api
                mock_games_api.list.return_value = response
                mock_api.return_value = mock_client

                games = services.fetch_upcoming_week_games(limit=3)

        self.assertEqual(len(games), 1)
        game = games[0]
        self.assertEqual(game['game_id'], '42')
        self.assertEqual(game['home_team_name'], 'Los Angeles Lakers')
        self.assertEqual(game['home_team_tricode'], 'LAL')
        self.assertEqual(game['away_team_name'], 'Boston Celtics')
        self.assertEqual(game['away_team_tricode'], 'BOS')
        self.assertEqual(game['arena'], 'Crypto.com Arena')
        self.assertIsNotNone(game['game_time'].tzinfo)

        mock_api.assert_called_once_with(api_key='Bearer secret-token')
        mock_games_api.list.assert_called_once_with(
            start_date='2024-01-11',
            end_date='2024-01-17',
            per_page=100,
            postseason=False,
        )

    def test_fetch_upcoming_week_games_handles_request_errors(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'secret-token'

        with mock.patch.object(services, 'BalldontlieAPI') as mock_api:
            mock_client = mock.Mock()
            mock_games_api = mock.Mock()
            mock_games_api.list.side_effect = exceptions.BallDontLieException('boom')
            mock_client.nba = mock.Mock()
            mock_client.nba.games = mock_games_api
            mock_api.return_value = mock_client

            games = services.fetch_upcoming_week_games(limit=2)

        self.assertEqual(games, [])
