"""Tests for NBA card rendering services."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from hooptipp.nba.services import (
    get_live_game_data,
    get_mvp_standings,
    get_player_card_data,
    get_team_logo_url,
    sync_players,
)
from hooptipp.nba.managers import NbaPlayerManager
from hooptipp.predictions.models import Option, OptionCategory


class GetTeamLogoUrlTests(TestCase):
    """Tests for get_team_logo_url function."""

    def setUp(self):
        cache.clear()
        self.teams_cat = OptionCategory.objects.create(
            slug="nba-teams",
            name="NBA Teams",
        )

    def tearDown(self):
        cache.clear()

    def test_returns_logo_url_for_nba_team_id(self):
        """Function should return CDN URL using NBA team ID."""
        url = get_team_logo_url("1610612738")  # Boston Celtics ID
        self.assertIn("1610612738", url)
        self.assertIn("logo", url.lower())
        self.assertIn("cdn.nba.com", url)

    def test_returns_logo_url_for_team_abbreviation(self):
        """Function should look up NBA team ID and return CDN URL."""
        # Create a team option with NBA team ID in metadata
        # Using BallDontLie ID 2 for Boston Celtics, which maps to NBA ID 1610612738
        team = Option.objects.create(
            category=self.teams_cat,
            slug="boston-celtics",
            name="Boston Celtics",
            short_name="BOS",
            external_id="2",  # BallDontLie ID
            metadata={
                "city": "Boston",
                "conference": "East",
                "division": "Atlantic",
                "nba_team_id": 1610612738,  # NBA team ID
                "balldontlie_team_id": 2,
            },
        )

        url = get_team_logo_url("BOS")
        self.assertIn("1610612738", url)
        self.assertIn("logo", url.lower())
        self.assertIn("cdn.nba.com", url)

    def test_returns_different_urls_for_different_teams(self):
        """Function should return different URLs for different teams."""
        # Create team options using BallDontLie IDs
        lakers = Option.objects.create(
            category=self.teams_cat,
            slug="los-angeles-lakers",
            name="Los Angeles Lakers",
            short_name="LAL",
            external_id="14",  # BallDontLie ID for Lakers
            metadata={
                "nba_team_id": 1610612747,  # NBA team ID for Lakers
                "balldontlie_team_id": 14,
            },
        )
        celtics = Option.objects.create(
            category=self.teams_cat,
            slug="boston-celtics",
            name="Boston Celtics",
            short_name="BOS",
            external_id="2",  # BallDontLie ID for Celtics
            metadata={
                "nba_team_id": 1610612738,  # NBA team ID for Celtics
                "balldontlie_team_id": 2,
            },
        )

        lal_url = get_team_logo_url("LAL")
        bos_url = get_team_logo_url("BOS")
        self.assertNotEqual(lal_url, bos_url)
        self.assertIn("1610612747", lal_url)
        self.assertIn("1610612738", bos_url)

    def test_falls_back_to_abbreviation_when_team_not_found(self):
        """Function should fall back to abbreviation when team not found in database."""
        url = get_team_logo_url("UNKNOWN")
        self.assertIn("UNKNOWN", url)
        self.assertIn("logo", url.lower())

    def test_caches_team_id_lookup(self):
        """Function should cache team ID lookups."""
        team = Option.objects.create(
            category=self.teams_cat,
            slug="boston-celtics",
            name="Boston Celtics",
            short_name="BOS",
            external_id="2",  # BallDontLie ID
            metadata={
                "nba_team_id": 1610612738,  # NBA team ID
                "balldontlie_team_id": 2,
            },
        )

        # First call
        url1 = get_team_logo_url("BOS")
        
        # Delete the team
        team.delete()
        
        # Second call should use cache
        url2 = get_team_logo_url("BOS")
        
        # Should still work from cache
        self.assertEqual(url1, url2)
        self.assertIn("1610612738", url2)

    def test_handles_case_insensitive_abbreviation(self):
        """Function should handle case insensitive team abbreviations."""
        team = Option.objects.create(
            category=self.teams_cat,
            slug="boston-celtics",
            name="Boston Celtics",
            short_name="BOS",
            external_id="2",  # BallDontLie ID
            metadata={
                "nba_team_id": 1610612738,  # NBA team ID
                "balldontlie_team_id": 2,
            },
        )

        url_lower = get_team_logo_url("bos")
        url_upper = get_team_logo_url("BOS")
        
        self.assertEqual(url_lower, url_upper)
        self.assertIn("1610612738", url_lower)


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
        mock_client.nba.games.get.return_value = mock_game

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
        mock_client.nba.games.get.return_value = mock_game

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
        mock_client.nba.games.get.return_value = mock_game

        with mock.patch("hooptipp.nba.services._build_bdl_client", return_value=mock_client):
            # First call
            data1 = get_live_game_data("12345")
            # Second call should use cache
            data2 = get_live_game_data("12345")

            # API should only be called once
            mock_client.nba.games.get.assert_called_once()
            self.assertEqual(data1, data2)

    def test_handles_api_errors_gracefully(self):
        """Function should handle API errors without crashing."""
        mock_client = mock.Mock()
        mock_client.nba.games.get.side_effect = Exception("API Error")

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
                mock_client.nba.games.get.return_value = mock_game

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
                mock_client.nba.games.get.return_value = mock_game

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


class PlayerSyncSlugUniquenessTests(TestCase):
    """Tests for player sync slug uniqueness to prevent duplicate constraint errors."""

    def setUp(self):
        """Set up test data."""
        # Use the same category creation method as the sync function
        self.players_cat = NbaPlayerManager.get_category()
        
        # Clear the BDL client cache to ensure fresh mocks
        from hooptipp.nba.services import _BDL_CLIENT_CACHE
        _BDL_CLIENT_CACHE.clear()

    def test_generates_unique_slugs_for_players_with_same_name(self):
        """Test that players with the same name get unique slugs."""
        # Mock the API response with players having the same name
        # Create mock player objects with attributes
        mock_player1 = mock.Mock()
        mock_player1.id = 1
        mock_player1.first_name = 'John'
        mock_player1.last_name = 'Smith'
        mock_player1.position = 'G'
        mock_player1.team.abbreviation = 'LAL'
        mock_player1.team.full_name = 'Los Angeles Lakers'
        
        mock_player2 = mock.Mock()
        mock_player2.id = 2
        mock_player2.first_name = 'John'
        mock_player2.last_name = 'Smith'
        mock_player2.position = 'F'
        mock_player2.team.abbreviation = 'BOS'
        mock_player2.team.full_name = 'Boston Celtics'
        
        mock_players = [mock_player1, mock_player2]
        
        # Mock the API client and API key
        with mock.patch('hooptipp.nba.services._get_bdl_api_key', return_value='test-api-key'):
            # Create a real client but mock its API calls
            from hooptipp.nba.services import _build_bdl_client
            client = _build_bdl_client()
            
            # Mock the API response
            mock_response = mock.Mock()
            mock_response.data = mock_players
            mock_response.meta = None
            
            # Mock the players.list method
            with mock.patch.object(client.nba.players, 'list', return_value=mock_response):
                # Run the sync
                result = sync_players()
                
                # Verify both players were created
                self.assertEqual(result.created, 2)
                
                # Verify both players have unique slugs
                players = Option.objects.filter(category=self.players_cat)
                slugs = [player.slug for player in players]
                
                # Should have unique slugs with player IDs
                self.assertIn('john-smith-1', slugs)
                self.assertIn('john-smith-2', slugs)
                self.assertEqual(len(set(slugs)), 2)  # All slugs should be unique

    def test_handles_special_characters_in_names(self):
        """Test that special characters in names are properly handled."""
        # Create mock player object with special characters
        mock_player = mock.Mock()
        mock_player.id = 3
        mock_player.first_name = "D'Angelo"
        mock_player.last_name = 'Russell'
        mock_player.position = 'G'
        mock_player.team.abbreviation = 'LAL'
        mock_player.team.full_name = 'Los Angeles Lakers'
        
        mock_players = [mock_player]
        
        with mock.patch('hooptipp.nba.services._get_bdl_api_key', return_value='test-api-key'):
            # Create a real client but mock its API calls
            from hooptipp.nba.services import _build_bdl_client
            client = _build_bdl_client()
            
            # Mock the API response
            mock_response = mock.Mock()
            mock_response.data = mock_players
            mock_response.meta = None
            
            # Mock the players.list method
            with mock.patch.object(client.nba.players, 'list', return_value=mock_response):
                result = sync_players()
                
                self.assertEqual(result.created, 1)
                
                player = Option.objects.filter(category=self.players_cat).first()
                # Special characters should be removed from slug
                self.assertEqual(player.slug, 'dangelo-russell-3')
