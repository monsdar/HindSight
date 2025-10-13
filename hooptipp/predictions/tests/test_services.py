import os
from datetime import datetime, timezone as dt_timezone
from unittest import TestCase, mock

from balldontlie import exceptions

from hooptipp.predictions import services


class GetBdlApiKeyTests(TestCase):
    def setUp(self) -> None:
        os.environ.pop('BALLDONTLIE_API_TOKEN', None)
        os.environ.pop('BALLDONTLIE_API_KEY', None)
        return super().setUp()

    def test_returns_bearer_prefix_for_token(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'secret-token'
        self.assertEqual(services._get_bdl_api_key(), 'Bearer secret-token')

    def test_supports_api_key_environment_variable(self) -> None:
        os.environ['BALLDONTLIE_API_KEY'] = 'another-token'
        self.assertEqual(services._get_bdl_api_key(), 'Bearer another-token')


class FetchUpcomingWeekGamesTests(TestCase):
    def setUp(self) -> None:
        os.environ.pop('BALLDONTLIE_API_TOKEN', None)
        os.environ.pop('BALLDONTLIE_API_KEY', None)
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
            with mock.patch.object(services, 'build_cached_bdl_client') as mock_builder:
                mock_client = mock.Mock()
                mock_games_api = mock.Mock()
                mock_client.nba = mock.Mock()
                mock_client.nba.games = mock_games_api
                mock_games_api.list.return_value = response
                mock_builder.return_value = mock_client

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

        mock_builder.assert_called_once_with(api_key='Bearer secret-token')
        mock_games_api.list.assert_called_once_with(
            start_date='2024-01-11',
            end_date='2024-02-09',
            per_page=100,
            postseason='false',
        )

    def test_fetch_upcoming_week_games_uses_first_available_week(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'secret-token'
        fake_now = datetime(2024, 7, 1, 12, 0, tzinfo=dt_timezone.utc)

        opener = mock.Mock(
            id=100,
            status='Scheduled',
            date='2024-10-20T23:00:00.000Z',
            home_team=mock.Mock(full_name='Boston Celtics', abbreviation='BOS'),
            visitor_team=mock.Mock(full_name='Los Angeles Lakers', abbreviation='LAL'),
            arena='TD Garden',
        )

        same_week = mock.Mock(
            id=101,
            status='Scheduled',
            date='2024-10-22T23:30:00.000Z',
            home_team=mock.Mock(full_name='Denver Nuggets', abbreviation='DEN'),
            visitor_team=mock.Mock(full_name='Phoenix Suns', abbreviation='PHX'),
            arena='Ball Arena',
        )

        later_game = mock.Mock(
            id=102,
            status='Scheduled',
            date='2024-10-30T00:30:00.000Z',
            home_team=mock.Mock(full_name='Miami Heat', abbreviation='MIA'),
            visitor_team=mock.Mock(full_name='New York Knicks', abbreviation='NYK'),
            arena='Kaseya Center',
        )

        response = mock.Mock(data=[opener, same_week, later_game])

        with mock.patch.object(services.timezone, 'now', return_value=fake_now):
            with mock.patch.object(services, 'build_cached_bdl_client') as mock_builder:
                mock_client = mock.Mock()
                mock_games_api = mock.Mock()
                mock_client.nba = mock.Mock()
                mock_client.nba.games = mock_games_api
                mock_games_api.list.return_value = response
                mock_builder.return_value = mock_client

                with mock.patch.object(services.random, 'shuffle', side_effect=lambda seq: None):
                    games = services.fetch_upcoming_week_games(limit=5)

        self.assertEqual(len(games), 2)
        returned_ids = {game['game_id'] for game in games}
        self.assertEqual(returned_ids, {'100', '101'})

    def test_fetch_upcoming_week_games_handles_request_errors(self) -> None:
        os.environ['BALLDONTLIE_API_TOKEN'] = 'secret-token'

        with mock.patch.object(services, 'build_cached_bdl_client') as mock_builder:
            mock_client = mock.Mock()
            mock_games_api = mock.Mock()
            mock_games_api.list.side_effect = exceptions.BallDontLieException('boom')
            mock_client.nba = mock.Mock()
            mock_client.nba.games = mock_games_api
            mock_builder.return_value = mock_client

            with self.assertLogs('hooptipp.predictions.services', level='ERROR') as captured:
                games = services.fetch_upcoming_week_games(limit=2)

        self.assertEqual(games, [])
        self.assertTrue(any('Unable to fetch games from BallDontLie API.' in entry for entry in captured.output))

    def test_logs_when_token_missing(self) -> None:
        with self.assertLogs('hooptipp.predictions.services', level='WARNING') as captured:
            games = services.fetch_upcoming_week_games(limit=2)

        self.assertEqual(games, [])
        self.assertTrue(any('BALLDONTLIE_API_TOKEN environment variable is not configured' in entry for entry in captured.output))
