"""Tests for NBA card rendering services."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from hooptipp.nba.services import (
    get_live_game_data,
    get_mvp_standings,
    get_player_card_data,
    get_team_logo_url,
)
from hooptipp.predictions.models import Option, OptionCategory


class GetTeamLogoUrlTests(TestCase):
    """Tests for get_team_logo_url function."""

    def test_returns_logo_url_for_tricode(self):
        """Function should return CDN URL for team logo."""
        url = get_team_logo_url("LAL")
        self.assertIn("LAL", url)
        self.assertIn("logo", url.lower())

    def test_returns_different_urls_for_different_teams(self):
        """Function should return different URLs for different teams."""
        lal_url = get_team_logo_url("LAL")
        bos_url = get_team_logo_url("BOS")
        self.assertNotEqual(lal_url, bos_url)


class GetLiveGameDataTests(TestCase):
    """Tests for get_live_game_data function."""

    def setUp(self):
        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        # Clear cache after each test
        cache.clear()

    def test_returns_default_data_when_no_client(self):
        """Function should return default data when client unavailable."""
        with mock.patch("hooptipp.nba.services._build_bdl_client", return_value=None):
            data = get_live_game_data("12345")

            self.assertIsNone(data["away_score"])
            self.assertIsNone(data["home_score"])
            self.assertEqual(data["game_status"], "")
            self.assertFalse(data["is_live"])

    def test_fetches_game_data_from_api(self):
        """Function should fetch game data from BallDontLie API."""
        mock_game = mock.Mock()
        mock_game.home_team_score = 110
        mock_game.visitor_team_score = 105
        mock_game.status = "Final"

        mock_client = mock.Mock()
        mock_client.nba.games.retrieve.return_value = mock_game

        with mock.patch("hooptipp.nba.services._build_bdl_client", return_value=mock_client):
            data = get_live_game_data("12345")

            self.assertEqual(data["home_score"], 110)
            self.assertEqual(data["away_score"], 105)
            self.assertEqual(data["game_status"], "Final")
            self.assertFalse(data["is_live"])

    def test_detects_live_games(self):
        """Function should detect when game is in progress."""
        mock_game = mock.Mock()
        mock_game.home_team_score = 85
        mock_game.visitor_team_score = 78
        mock_game.status = "Q3"

        mock_client = mock.Mock()
        mock_client.nba.games.retrieve.return_value = mock_game

        with mock.patch("hooptipp.nba.services._build_bdl_client", return_value=mock_client):
            data = get_live_game_data("12345")

            self.assertTrue(data["is_live"])

    def test_caches_live_data(self):
        """Function should cache live game data."""
        mock_game = mock.Mock()
        mock_game.home_team_score = 110
        mock_game.visitor_team_score = 105
        mock_game.status = "Final"

        mock_client = mock.Mock()
        mock_client.nba.games.retrieve.return_value = mock_game

        with mock.patch("hooptipp.nba.services._build_bdl_client", return_value=mock_client):
            # First call
            data1 = get_live_game_data("12345")
            # Second call should use cache
            data2 = get_live_game_data("12345")

            # API should only be called once
            mock_client.nba.games.retrieve.assert_called_once()
            self.assertEqual(data1, data2)

    def test_handles_api_errors_gracefully(self):
        """Function should handle API errors without crashing."""
        mock_client = mock.Mock()
        mock_client.nba.games.retrieve.side_effect = Exception("API Error")

        with mock.patch("hooptipp.nba.services._build_bdl_client", return_value=mock_client):
            data = get_live_game_data("12345")

            # Should return default data
            self.assertIsNone(data["away_score"])
            self.assertIsNone(data["home_score"])

    def test_multiple_live_statuses(self):
        """Function should detect various live game statuses."""
        statuses_live = ["Q1", "Q2", "Q3", "Q4", "OT", "Halftime", "HALFTIME"]
        statuses_not_live = ["Final", "Scheduled", "Postponed"]

        mock_client = mock.Mock()

        with mock.patch("hooptipp.nba.services._build_bdl_client", return_value=mock_client):
            for status in statuses_live:
                mock_game = mock.Mock()
                mock_game.home_team_score = 50
                mock_game.visitor_team_score = 48
                mock_game.status = status
                mock_client.nba.games.retrieve.return_value = mock_game

                cache.clear()  # Clear cache between tests
                data = get_live_game_data("12345")
                self.assertTrue(
                    data["is_live"], f"Status '{status}' should be detected as live"
                )

            for status in statuses_not_live:
                mock_game = mock.Mock()
                mock_game.home_team_score = 110
                mock_game.visitor_team_score = 105
                mock_game.status = status
                mock_client.nba.games.retrieve.return_value = mock_game

                cache.clear()
                data = get_live_game_data("12345")
                self.assertFalse(
                    data["is_live"],
                    f"Status '{status}' should not be detected as live",
                )


class GetPlayerCardDataTests(TestCase):
    """Tests for get_player_card_data function."""

    def setUp(self):
        cache.clear()
        self.players_cat = OptionCategory.objects.create(
            slug="nba-players",
            name="NBA Players",
        )

    def tearDown(self):
        cache.clear()

    def test_returns_player_data_from_option(self):
        """Function should return player data from Option model."""
        player = Option.objects.create(
            category=self.players_cat,
            slug="lebron-james",
            name="LeBron James",
            external_id="123",
            metadata={
                "position": "F",
                "team_name": "Los Angeles Lakers",
                "team_abbreviation": "LAL",
            },
        )

        data = get_player_card_data("123")

        self.assertEqual(data["team"], "Los Angeles Lakers")
        self.assertEqual(data["team_tricode"], "LAL")
        self.assertEqual(data["position"], "F")
        self.assertIsNone(data["portrait_url"])  # Not implemented yet
        self.assertIsNone(data["current_stats"])  # Not implemented yet

    def test_returns_default_data_for_missing_player(self):
        """Function should return default data when player not found."""
        data = get_player_card_data("999")

        self.assertEqual(data["team"], "")
        self.assertEqual(data["team_tricode"], "")
        self.assertEqual(data["position"], "")
        self.assertIsNone(data["portrait_url"])

    def test_caches_player_data(self):
        """Function should cache player card data."""
        player = Option.objects.create(
            category=self.players_cat,
            slug="lebron-james",
            name="LeBron James",
            external_id="123",
            metadata={
                "position": "F",
                "team_name": "Los Angeles Lakers",
                "team_abbreviation": "LAL",
            },
        )

        # First call
        data1 = get_player_card_data("123")

        # Delete the player
        player.delete()

        # Second call should use cache
        data2 = get_player_card_data("123")

        # Should still have the data from cache
        self.assertEqual(data1, data2)
        self.assertEqual(data2["team"], "Los Angeles Lakers")

    def test_handles_missing_metadata_gracefully(self):
        """Function should handle missing metadata fields."""
        player = Option.objects.create(
            category=self.players_cat,
            slug="player",
            name="Test Player",
            external_id="456",
            metadata={},  # Empty metadata
        )

        data = get_player_card_data("456")

        # Should have default empty strings
        self.assertEqual(data["team"], "")
        self.assertEqual(data["team_tricode"], "")
        self.assertEqual(data["position"], "")


class GetMvpStandingsTests(TestCase):
    """Tests for get_mvp_standings function."""

    def test_returns_empty_list(self):
        """Function should return empty list (placeholder implementation)."""
        standings = get_mvp_standings()

        self.assertIsInstance(standings, list)
        self.assertEqual(len(standings), 0)
