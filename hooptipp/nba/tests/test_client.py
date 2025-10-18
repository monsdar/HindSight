from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import TestCase, mock

from hooptipp.nba.client import CachedBallDontLieAPI


class CachedGamesAPITests(TestCase):
    def setUp(self) -> None:
        self.fake_now = datetime(2024, 1, 10, 12, 0, tzinfo=dt_timezone.utc)
        self.mock_games_api = mock.Mock()
        nba_api = mock.Mock(games=self.mock_games_api)
        base_client = mock.Mock(nba=nba_api)
        self.client = CachedBallDontLieAPI(base_client)
        super().setUp()

    def test_list_is_cached_until_game_starts(self) -> None:
        scheduled_game = mock.Mock(status='Scheduled', date='2024-01-10T20:00:00.000Z')
        response = mock.Mock(data=[scheduled_game])
        self.mock_games_api.list.return_value = response

        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now):
            first = self.client.nba.games.list(start_date='2024-01-11')

        self.assertIs(first, response)
        self.mock_games_api.list.assert_called_once()

        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now + timedelta(hours=1)):
            second = self.client.nba.games.list(start_date='2024-01-11')

        self.assertIs(second, response)
        self.mock_games_api.list.assert_called_once()

        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now + timedelta(hours=10)):
            self.client.nba.games.list(start_date='2024-01-11')

        self.assertEqual(self.mock_games_api.list.call_count, 2)

    def test_get_caches_final_games_indefinitely(self) -> None:
        final_game = mock.Mock(status='Final')
        response = mock.Mock(data=final_game)
        self.mock_games_api.get.return_value = response

        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now):
            first = self.client.nba.games.get(99)

        self.assertIs(first, response)
        self.mock_games_api.get.assert_called_once_with(99)

        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now + timedelta(days=7)):
            second = self.client.nba.games.get(99)

        self.assertIs(second, response)
        self.mock_games_api.get.assert_called_once_with(99)

    def test_get_refreshes_in_progress_games(self) -> None:
        in_progress_game = mock.Mock(status='In Progress')
        response = mock.Mock(data=in_progress_game)
        self.mock_games_api.get.return_value = response

        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now):
            self.client.nba.games.get(7)

        self.mock_games_api.get.assert_called_once_with(7)

        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now + timedelta(seconds=30)):
            self.client.nba.games.get(7)

        self.assertEqual(self.mock_games_api.get.call_count, 1)

        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now + timedelta(minutes=2)):
            self.client.nba.games.get(7)

        self.assertEqual(self.mock_games_api.get.call_count, 2)
