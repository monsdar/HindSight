"""Tests for SLAPI client."""

import os
from unittest.mock import MagicMock, patch

from django.test import TestCase

from hooptipp.dbb.client import SlapiClient, build_slapi_client


class SlapiClientTest(TestCase):
    """Tests for SlapiClient."""

    def setUp(self):
        """Set up test client."""
        self.client = SlapiClient(api_token='test_token')

    @patch('hooptipp.dbb.client.requests.Session.get')
    def test_get_verbaende(self, mock_get):
        """Test fetching Verbände."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {'id': '100', 'label': 'Bundesligen', 'hits': 34},
            {'id': '101', 'label': 'Landesverbände', 'hits': 22}
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.client.get_verbaende()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['label'], 'Bundesligen')
        self.assertEqual(result[0]['hits'], 34)
        mock_get.assert_called_once()

    @patch('hooptipp.dbb.client.requests.Session.get')
    def test_get_club_leagues_with_search(self, mock_get):
        """Test fetching leagues for a club search term."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'club_name': 'Bierden-Bassen',
            'verband_id': 7,
            'leagues': [
                {'liga_id': 48693, 'liganame': 'Regionsliga Süd Herren', 'spielklasse': 'Regionsliga'},
                {'liga_id': 48694, 'liganame': 'Regionsliga Mixed', 'spielklasse': 'Regionsliga'}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.client.get_club_leagues('7', 'Bierden-Bassen')

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['liganame'], 'Regionsliga Süd Herren')
        self.assertEqual(result[0]['liga_id'], 48693)
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        # Check that it's using the correct endpoint
        self.assertIn('/clubs/Bierden-Bassen/leagues', args[0])
        self.assertEqual(kwargs['params'], {'verband_id': '7'})


    @patch('hooptipp.dbb.client.requests.Session.get')
    def test_get_league_standings(self, mock_get):
        """Test fetching league standings."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'league_id': '48693',
            'standings': [
                {'position': 1, 'team': {'id': 't1', 'name': 'Team 1'}, 'wins': 10, 'losses': 2},
                {'position': 2, 'team': {'id': 't2', 'name': 'Team 2'}, 'wins': 9, 'losses': 3}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.client.get_league_standings('48693')

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['team']['name'], 'Team 1')
        self.assertEqual(result[0]['position'], 1)

    @patch('hooptipp.dbb.client.requests.Session.get')
    def test_get_league_matches(self, mock_get):
        """Test fetching league matches."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'league_id': '48693',
            'matches': [
                {'match_id': 1, 'home_team': {'name': 'Team A'}, 'away_team': {'name': 'Team B'}, 'datetime': '2025-01-01T18:00:00'},
                {'match_id': 2, 'home_team': {'name': 'Team C'}, 'away_team': {'name': 'Team D'}, 'datetime': '2025-01-02T18:00:00'}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.client.get_league_matches('48693')

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['home_team']['name'], 'Team A')
        self.assertEqual(result[0]['match_id'], 1)

    @patch('hooptipp.dbb.client.requests.Session.get')
    def test_get_match_details(self, mock_get):
        """Test fetching match details."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'id': 'm1',
            'home_team': 'Team A',
            'away_team': 'Team B',
            'home_score': 85,
            'away_score': 78
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.client.get_match_details('match_123')

        self.assertEqual(result['home_score'], 85)
        self.assertEqual(result['away_score'], 78)

    def test_authentication_header(self):
        """Test that authentication header is set correctly."""
        client = SlapiClient(api_token='my_token')
        self.assertEqual(client.session.headers['Authorization'], 'Bearer my_token')

    @patch.dict(os.environ, {'SLAPI_API_TOKEN': 'env_token'})
    def test_build_slapi_client_with_env(self):
        """Test building client with environment variable."""
        client = build_slapi_client()
        self.assertIsNotNone(client)
        self.assertEqual(client.api_token, 'env_token')

    @patch.dict(os.environ, {}, clear=True)
    def test_build_slapi_client_without_token(self):
        """Test building client without token returns None."""
        # Clear SLAPI_API_TOKEN from environment
        if 'SLAPI_API_TOKEN' in os.environ:
            del os.environ['SLAPI_API_TOKEN']
        
        client = build_slapi_client()
        self.assertIsNone(client)

    @patch('hooptipp.dbb.client.requests.Session.get')
    def test_get_verbaende_wrapped_response(self, mock_get):
        """Test fetching Verbände with wrapped response structure."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'verbaende': [
                {'id': '100', 'label': 'Bundesligen', 'hits': 34},
                {'id': '101', 'label': 'Landesverbände', 'hits': 22}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.client.get_verbaende()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['label'], 'Bundesligen')

    @patch('hooptipp.dbb.client.requests.Session.get')
    def test_get_club_leagues_list_response(self, mock_get):
        """Test fetching club leagues with direct list response (backward compatibility)."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {'liga_id': 48693, 'liganame': 'League 1'},
            {'liga_id': 48694, 'liganame': 'League 2'}
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.client.get_club_leagues('7', 'Test Club')

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['liganame'], 'League 1')

    @patch('hooptipp.dbb.client.requests.Session.get')
    def test_get_verbaende_data_wrapper(self, mock_get):
        """Test fetching Verbände with generic 'data' wrapper."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'data': [
                {'id': '100', 'label': 'Bundesligen', 'hits': 34},
                {'id': '101', 'label': 'Landesverbände', 'hits': 22}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.client.get_verbaende()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['label'], 'Bundesligen')

    @patch('hooptipp.dbb.client.requests.Session.get')
    def test_get_verbaende_empty_response(self, mock_get):
        """Test fetching Verbände with empty list."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.client.get_verbaende()

        self.assertEqual(len(result), 0)
        self.assertIsInstance(result, list)

