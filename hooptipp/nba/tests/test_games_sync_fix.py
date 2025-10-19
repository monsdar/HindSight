"""Test for NBA games sync fix to handle dict responses from BallDontLie API."""

from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hooptipp.predictions.models import Option, OptionCategory


User = get_user_model()


class NbaGamesSyncFixTest(TestCase):
    """Test that NBA games sync properly handles dict responses from BallDontLie API."""

    def setUp(self):
        """Set up test fixtures."""
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123',
        )
        self.client.force_login(self.admin_user)
        
        # Create option categories
        self.teams_category, _ = OptionCategory.objects.get_or_create(
            slug='nba-teams',
            defaults={
                'name': 'NBA Teams',
                'description': 'NBA teams',
                'icon': 'basketball',
            },
        )

    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_add_upcoming_games_handles_dict_response(self, mock_build_client):
        """Test that add_upcoming_games_view handles dict responses from BallDontLie API."""
        # Mock the client and response
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Create mock game data as dict (which is what BallDontLie actually returns)
        future_time = timezone.now() + timedelta(days=1)
        mock_game_data = {
            'id': 12345,
            'datetime': future_time.isoformat(),
            'status': 'Scheduled',
            'home_team': {
                'id': 1,
                'full_name': 'Los Angeles Lakers',
                'name': 'Lakers',
                'abbreviation': 'LAL',
                'city': 'Los Angeles',
                'conference': 'West',
                'division': 'Pacific',
            },
            'visitor_team': {
                'id': 2,
                'full_name': 'Boston Celtics',
                'name': 'Celtics',
                'abbreviation': 'BOS',
                'city': 'Boston',
                'conference': 'East',
                'division': 'Atlantic',
            },
            'arena': 'Crypto.com Arena',
        }
        
        # Mock the API response
        mock_response = MagicMock()
        mock_response.data = [mock_game_data]
        mock_client.nba.games.list.return_value = mock_response
        
        # Make the request
        url = reverse('admin:nba_add_upcoming_games')
        response = self.client.get(url)
        
        # Should succeed and show games (not "No upcoming games found")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add Upcoming NBA Games')
        self.assertContains(response, 'LAL')  # Home team abbreviation
        self.assertContains(response, 'BOS')  # Away team abbreviation
        self.assertNotContains(response, 'No upcoming games found')

    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_add_upcoming_games_handles_object_response(self, mock_build_client):
        """Test that add_upcoming_games_view still works with object responses."""
        # Mock the client and response
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Create mock game data as object (legacy format)
        future_time = timezone.now() + timedelta(days=1)
        mock_game = MagicMock()
        mock_game.id = 12345
        mock_game.datetime = future_time.isoformat()
        # Status contains tip-off time for scheduled games (format: 2025-10-21T23:30:00Z)
        mock_game.status = future_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        mock_game.arena = 'Crypto.com Arena'
        
        # Mock team objects
        mock_home_team = MagicMock()
        mock_home_team.id = 1
        mock_home_team.full_name = 'Los Angeles Lakers'
        mock_home_team.name = 'Lakers'
        mock_home_team.abbreviation = 'LAL'
        mock_home_team.city = 'Los Angeles'
        mock_home_team.conference = 'West'
        mock_home_team.division = 'Pacific'
        
        mock_visitor_team = MagicMock()
        mock_visitor_team.id = 2
        mock_visitor_team.full_name = 'Boston Celtics'
        mock_visitor_team.name = 'Celtics'
        mock_visitor_team.abbreviation = 'BOS'
        mock_visitor_team.city = 'Boston'
        mock_visitor_team.conference = 'East'
        mock_visitor_team.division = 'Atlantic'
        
        mock_game.home_team = mock_home_team
        mock_game.visitor_team = mock_visitor_team
        
        # Mock the API response
        mock_response = MagicMock()
        mock_response.data = [mock_game]
        mock_client.nba.games.list.return_value = mock_response
        
        # Make the request
        url = reverse('admin:nba_add_upcoming_games')
        response = self.client.get(url)
        
        # Should succeed and show games
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add Upcoming NBA Games')
        self.assertContains(response, 'LAL')  # Home team abbreviation
        self.assertContains(response, 'BOS')  # Away team abbreviation
        self.assertNotContains(response, 'No upcoming games found')

    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_add_upcoming_games_filters_final_games(self, mock_build_client):
        """Test that final games are properly filtered out."""
        # Mock the client and response
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Create mock game data with final status
        future_time = timezone.now() + timedelta(days=1)
        mock_game_data = {
            'id': 12345,
            'datetime': future_time.isoformat(),
            'status': 'Final',  # This should be filtered out
            'home_team': {
                'id': 1,
                'full_name': 'Los Angeles Lakers',
                'name': 'Lakers',
                'abbreviation': 'LAL',
                'city': 'Los Angeles',
                'conference': 'West',
                'division': 'Pacific',
            },
            'visitor_team': {
                'id': 2,
                'full_name': 'Boston Celtics',
                'name': 'Celtics',
                'abbreviation': 'BOS',
                'city': 'Boston',
                'conference': 'East',
                'division': 'Atlantic',
            },
            'arena': 'Crypto.com Arena',
        }
        
        # Mock the API response
        mock_response = MagicMock()
        mock_response.data = [mock_game_data]
        mock_client.nba.games.list.return_value = mock_response
        
        # Make the request
        url = reverse('admin:nba_add_upcoming_games')
        response = self.client.get(url)
        
        # Should show "No upcoming games found" because the game is final
        self.assertEqual(response.status_code, 302)  # Redirects to admin index
        # The message would be in the redirect, but we can't easily test it here
        # The important thing is that it doesn't crash and handles the filtering correctly

    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_add_upcoming_games_filters_past_games(self, mock_build_client):
        """Test that past games are properly filtered out."""
        # Mock the client and response
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Create mock game data with past time
        past_time = timezone.now() - timedelta(days=1)
        mock_game_data = {
            'id': 12345,
            'datetime': past_time.isoformat(),
            'status': 'Scheduled',
            'home_team': {
                'id': 1,
                'full_name': 'Los Angeles Lakers',
                'name': 'Lakers',
                'abbreviation': 'LAL',
                'city': 'Los Angeles',
                'conference': 'West',
                'division': 'Pacific',
            },
            'visitor_team': {
                'id': 2,
                'full_name': 'Boston Celtics',
                'name': 'Celtics',
                'abbreviation': 'BOS',
                'city': 'Boston',
                'conference': 'East',
                'division': 'Atlantic',
            },
            'arena': 'Crypto.com Arena',
        }
        
        # Mock the API response
        mock_response = MagicMock()
        mock_response.data = [mock_game_data]
        mock_client.nba.games.list.return_value = mock_response
        
        # Make the request
        url = reverse('admin:nba_add_upcoming_games')
        response = self.client.get(url)
        
        # Should show "No upcoming games found" because the game is in the past
        self.assertEqual(response.status_code, 302)  # Redirects to admin index
