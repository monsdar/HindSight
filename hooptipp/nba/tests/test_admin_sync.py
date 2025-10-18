"""Tests for NBA admin sync functionality."""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from hooptipp.nba.services import SyncResult
from hooptipp.predictions.models import Option, OptionCategory


User = get_user_model()


class NbaSyncViewTest(TestCase):
    """Test the NBA sync admin views."""

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
        
        self.players_category, _ = OptionCategory.objects.get_or_create(
            slug='nba-players',
            defaults={
                'name': 'NBA Players',
                'description': 'NBA players',
                'icon': 'person',
            },
        )

    def test_sync_view_get(self):
        """Test GET request to sync page displays properly."""
        url = reverse('admin:nba_sync')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'NBA Data Synchronization')
        self.assertContains(response, 'Sync Teams')
        self.assertContains(response, 'Sync Players')

    def test_sync_view_permissions(self):
        """Test that non-admin users cannot access sync page."""
        regular_user = User.objects.create_user(
            username='regular',
            email='regular@test.com',
            password='testpass123',
        )
        self.client.force_login(regular_user)
        
        url = reverse('admin:nba_sync')
        response = self.client.get(url)
        
        # Should redirect to login or show permission denied
        self.assertIn(response.status_code, [302, 403])

    @patch('hooptipp.nba.admin.sync_teams')
    def test_sync_teams_success(self, mock_sync_teams):
        """Test successful team synchronization."""
        # Mock the sync result
        mock_sync_teams.return_value = SyncResult(created=5, updated=10, removed=2)
        
        url = reverse('admin:nba_sync_teams')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('admin:nba_sync'))
        
        # Verify sync_teams was called
        mock_sync_teams.assert_called_once()
        
        # Check success message
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn('5 team(s) created', str(messages[0]))
        self.assertIn('10 team(s) updated', str(messages[0]))
        self.assertIn('2 team(s) removed', str(messages[0]))

    @patch('hooptipp.nba.admin.sync_teams')
    def test_sync_teams_no_changes(self, mock_sync_teams):
        """Test team sync with no changes."""
        mock_sync_teams.return_value = SyncResult(created=0, updated=0, removed=0)
        
        url = reverse('admin:nba_sync_teams')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn('no changes', str(messages[0]).lower())

    @patch('hooptipp.nba.admin.sync_teams')
    def test_sync_teams_error(self, mock_sync_teams):
        """Test team sync with error."""
        mock_sync_teams.side_effect = Exception('API connection failed')
        
        url = reverse('admin:nba_sync_teams')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn('Failed to sync teams', str(messages[0]))
        self.assertIn('API connection failed', str(messages[0]))

    @patch('hooptipp.nba.admin.sync_players')
    def test_sync_players_success(self, mock_sync_players):
        """Test successful player synchronization."""
        mock_sync_players.return_value = SyncResult(created=50, updated=400, removed=10)
        
        url = reverse('admin:nba_sync_players')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('admin:nba_sync'))
        
        # Verify sync_players was called
        mock_sync_players.assert_called_once()
        
        # Check messages
        messages = list(response.wsgi_request._messages)
        # Should have 2 messages: info about sync starting and success
        self.assertGreaterEqual(len(messages), 1)
        
        # Check for success message
        success_messages = [m for m in messages if 'successfully' in str(m).lower()]
        self.assertGreater(len(success_messages), 0)
        self.assertIn('50 player(s) created', str(success_messages[0]))
        self.assertIn('400 player(s) updated', str(success_messages[0]))
        self.assertIn('10 player(s) removed', str(success_messages[0]))

    @patch('hooptipp.nba.admin.sync_players')
    def test_sync_players_no_changes(self, mock_sync_players):
        """Test player sync with no changes."""
        mock_sync_players.return_value = SyncResult(created=0, updated=0, removed=0)
        
        url = reverse('admin:nba_sync_players')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        
        messages = list(response.wsgi_request._messages)
        # Should have messages about starting and no changes
        self.assertGreaterEqual(len(messages), 1)

    @patch('hooptipp.nba.admin.sync_players')
    def test_sync_players_error(self, mock_sync_players):
        """Test player sync with error."""
        mock_sync_players.side_effect = Exception('Rate limit exceeded')
        
        url = reverse('admin:nba_sync_players')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        
        messages = list(response.wsgi_request._messages)
        # Find error message
        error_messages = [m for m in messages if 'failed' in str(m).lower()]
        self.assertGreater(len(error_messages), 0)
        self.assertIn('Rate limit exceeded', str(error_messages[0]))

    def test_sync_teams_get_not_allowed(self):
        """Test that GET requests to sync_teams are not allowed."""
        url = reverse('admin:nba_sync_teams')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 405)  # Method Not Allowed

    def test_sync_players_get_not_allowed(self):
        """Test that GET requests to sync_players are not allowed."""
        url = reverse('admin:nba_sync_players')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 405)  # Method Not Allowed

    def test_sync_teams_permissions(self):
        """Test that non-admin users cannot sync teams."""
        regular_user = User.objects.create_user(
            username='regular',
            email='regular@test.com',
            password='testpass123',
        )
        self.client.force_login(regular_user)
        
        url = reverse('admin:nba_sync_teams')
        response = self.client.post(url)
        
        # Should redirect to login or show permission denied
        self.assertIn(response.status_code, [302, 403])

    def test_sync_players_permissions(self):
        """Test that non-admin users cannot sync players."""
        regular_user = User.objects.create_user(
            username='regular',
            email='regular@test.com',
            password='testpass123',
        )
        self.client.force_login(regular_user)
        
        url = reverse('admin:nba_sync_players')
        response = self.client.post(url)
        
        # Should redirect to login or show permission denied
        self.assertIn(response.status_code, [302, 403])

    @patch('hooptipp.nba.admin.sync_teams')
    def test_sync_teams_partial_result(self, mock_sync_teams):
        """Test team sync with only some operations."""
        # Only created, no updates or removals
        mock_sync_teams.return_value = SyncResult(created=3, updated=0, removed=0)
        
        url = reverse('admin:nba_sync_teams')
        response = self.client.post(url)
        
        messages = list(response.wsgi_request._messages)
        message_text = str(messages[0])
        
        self.assertIn('3 team(s) created', message_text)
        self.assertNotIn('updated', message_text.lower())
        self.assertNotIn('removed', message_text.lower())

    @patch('hooptipp.nba.admin.sync_players')
    def test_sync_players_partial_result(self, mock_sync_players):
        """Test player sync with only updates."""
        # Only updated, no creates or removals
        mock_sync_players.return_value = SyncResult(created=0, updated=100, removed=0)
        
        url = reverse('admin:nba_sync_players')
        response = self.client.post(url)
        
        messages = list(response.wsgi_request._messages)
        success_messages = [m for m in messages if 'successfully' in str(m).lower()]
        message_text = str(success_messages[0])
        
        self.assertIn('100 player(s) updated', message_text)
        self.assertNotIn('created', message_text.lower())
        self.assertNotIn('removed', message_text.lower())
