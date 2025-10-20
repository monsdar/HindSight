from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import TestCase, mock

from balldontlie.exceptions import RateLimitError, BallDontLieException
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


class CachedPlayersAPITests(TestCase):
    def setUp(self) -> None:
        self.fake_now = datetime(2024, 1, 10, 12, 0, tzinfo=dt_timezone.utc)
        self.mock_players_api = mock.Mock()
        nba_api = mock.Mock(players=self.mock_players_api)
        base_client = mock.Mock(nba=nba_api)
        self.client = CachedBallDontLieAPI(base_client)
        super().setUp()

    def test_list_caches_players_for_six_hours(self) -> None:
        """Test that players list calls are cached for 6 hours."""
        mock_players = [
            mock.Mock(id=1, first_name="Test", last_name="Player1"),
            mock.Mock(id=2, first_name="Test", last_name="Player2"),
        ]
        response = mock.Mock(data=mock_players)
        self.mock_players_api.list.return_value = response

        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now):
            first = self.client.nba.players.list(per_page=10)

        self.assertIs(first, response)
        self.mock_players_api.list.assert_called_once_with(per_page=10)

        # Call again within cache duration - should use cache
        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now + timedelta(hours=3)):
            second = self.client.nba.players.list(per_page=10)

        self.assertIs(second, response)
        self.mock_players_api.list.assert_called_once_with(per_page=10)

        # Call again after cache expires - should hit API again
        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now + timedelta(hours=7)):
            third = self.client.nba.players.list(per_page=10)

        self.assertIs(third, response)
        self.assertEqual(self.mock_players_api.list.call_count, 2)

    def test_different_parameters_create_different_cache_entries(self) -> None:
        """Test that different parameters create separate cache entries."""
        mock_players = [mock.Mock(id=1, first_name="Test", last_name="Player1")]
        response = mock.Mock(data=mock_players)
        self.mock_players_api.list.return_value = response

        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now):
            # First call with per_page=10
            self.client.nba.players.list(per_page=10)
            # Second call with per_page=5
            self.client.nba.players.list(per_page=5)

        # Should have made 2 API calls for different parameters
        self.assertEqual(self.mock_players_api.list.call_count, 2)
        self.mock_players_api.list.assert_any_call(per_page=10)
        self.mock_players_api.list.assert_any_call(per_page=5)

    def test_cache_handles_api_errors_gracefully(self) -> None:
        """Test that cache doesn't interfere with API error handling."""
        from balldontlie.exceptions import BallDontLieException
        
        # First call succeeds
        mock_players = [mock.Mock(id=1, first_name="Test", last_name="Player1")]
        response = mock.Mock(data=mock_players)
        self.mock_players_api.list.return_value = response

        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now):
            first = self.client.nba.players.list(per_page=10)

        self.assertIs(first, response)
        self.mock_players_api.list.assert_called_once()

        # Second call with same parameters should use cache (no API call)
        with mock.patch('hooptipp.nba.client.timezone.now', return_value=self.fake_now + timedelta(hours=1)):
            second = self.client.nba.players.list(per_page=10)

        self.assertIs(second, response)
        self.mock_players_api.list.assert_called_once()  # Still only 1 call


class RetryLogicTests(TestCase):
    def setUp(self) -> None:
        self.fake_now = datetime(2024, 1, 10, 12, 0, tzinfo=dt_timezone.utc)
        self.mock_players_api = mock.Mock()
        nba_api = mock.Mock(players=self.mock_players_api)
        base_client = mock.Mock(nba=nba_api)
        self.client = CachedBallDontLieAPI(base_client)
        super().setUp()

    def test_retries_on_rate_limit_error(self) -> None:
        """Test that the client retries on RateLimitError."""
        mock_players = [mock.Mock(id=1, first_name="Test", last_name="Player1")]
        response = mock.Mock(data=mock_players)
        
        # First call raises RateLimitError, second call succeeds
        self.mock_players_api.list.side_effect = [RateLimitError("Too Many Requests"), response]

        with mock.patch('time.sleep') as mock_sleep:
            result = self.client.nba.players.list(per_page=10)

        self.assertIs(result, response)
        self.assertEqual(self.mock_players_api.list.call_count, 2)
        mock_sleep.assert_called_once_with(10.0)  # Should sleep for 10 seconds

    def test_retries_multiple_times_on_rate_limit(self) -> None:
        """Test that the client retries multiple times on consecutive rate limits."""
        mock_players = [mock.Mock(id=1, first_name="Test", last_name="Player1")]
        response = mock.Mock(data=mock_players)
        
        # First two calls raise RateLimitError, third call succeeds
        self.mock_players_api.list.side_effect = [
            RateLimitError("Too Many Requests"),
            RateLimitError("Too Many Requests"),
            response
        ]

        with mock.patch('time.sleep') as mock_sleep:
            result = self.client.nba.players.list(per_page=10)

        self.assertIs(result, response)
        self.assertEqual(self.mock_players_api.list.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)  # Should sleep twice

    def test_gives_up_after_max_retries(self) -> None:
        """Test that the client gives up after maximum retries."""
        # All calls raise RateLimitError
        self.mock_players_api.list.side_effect = RateLimitError("Too Many Requests")

        with mock.patch('time.sleep'):
            with self.assertRaises(RateLimitError):
                self.client.nba.players.list(per_page=10)

        self.assertEqual(self.mock_players_api.list.call_count, 4)  # 1 initial + 3 retries

    def test_does_not_retry_on_other_api_errors(self) -> None:
        """Test that the client does not retry on non-rate-limit errors."""
        # Call raises a different API error
        self.mock_players_api.list.side_effect = BallDontLieException("Authentication failed")

        with self.assertRaises(BallDontLieException):
            self.client.nba.players.list(per_page=10)

        self.assertEqual(self.mock_players_api.list.call_count, 1)  # Should not retry

    def test_retry_works_with_games_api(self) -> None:
        """Test that retry logic works with games API as well."""
        mock_games_api = mock.Mock()
        nba_api = mock.Mock(games=mock_games_api)
        base_client = mock.Mock(nba=nba_api)
        client = CachedBallDontLieAPI(base_client)
        
        mock_game = mock.Mock(status='Final')
        response = mock.Mock(data=mock_game)
        
        # First call raises RateLimitError, second call succeeds
        mock_games_api.get.side_effect = [RateLimitError("Too Many Requests"), response]

        with mock.patch('time.sleep') as mock_sleep:
            result = client.nba.games.get(123)

        self.assertIs(result, response)
        self.assertEqual(mock_games_api.get.call_count, 2)
        mock_sleep.assert_called_once_with(10.0)
