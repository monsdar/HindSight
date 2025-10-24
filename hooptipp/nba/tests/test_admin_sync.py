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

    @patch('hooptipp.nba.admin.threading.Thread')
    def test_sync_players_success(self, mock_thread_class):
        """Test player synchronization starts in background thread."""
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread
        
        url = reverse('admin:nba_sync_players')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('admin:nba_sync'))
        
        # Verify thread was created and started
        mock_thread_class.assert_called_once()
        mock_thread.start.assert_called_once()
        
        # Check that thread was created with correct parameters
        call_kwargs = mock_thread_class.call_args[1]
        self.assertTrue(call_kwargs.get('daemon'))
        self.assertEqual(call_kwargs.get('name'), 'nba-player-sync')
        
        # Check messages - should indicate background sync started
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn('started in the background', str(messages[0]).lower())

    @patch('hooptipp.nba.admin.threading.Thread')
    def test_sync_players_no_changes(self, mock_thread_class):
        """Test player sync starts in background."""
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread
        
        url = reverse('admin:nba_sync_players')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        
        # Verify thread was started
        mock_thread.start.assert_called_once()
        
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn('started in the background', str(messages[0]).lower())

    @patch('hooptipp.nba.admin.threading.Thread')
    def test_sync_players_starts_thread(self, mock_thread_class):
        """Test player sync starts background thread."""
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread
        
        url = reverse('admin:nba_sync_players')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 302)
        
        # Verify thread was created and started
        mock_thread_class.assert_called_once()
        mock_thread.start.assert_called_once()
        
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn('started in the background', str(messages[0]).lower())

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

    @patch('hooptipp.nba.admin.threading.Thread')
    def test_sync_players_returns_immediately(self, mock_thread_class):
        """Test player sync returns immediately without waiting for completion."""
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread
        
        url = reverse('admin:nba_sync_players')
        response = self.client.post(url)
        
        # Should return immediately (302) without waiting for sync to complete
        self.assertEqual(response.status_code, 302)
        
        # Thread should be started but we don't wait for it
        mock_thread.start.assert_called_once()
        
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn('started in the background', str(messages[0]).lower())

    @patch('hooptipp.nba.admin.sync_players_from_hoopshype')
    @patch('hooptipp.nba.admin.logger')
    def test_background_sync_logs_success(self, mock_logger, mock_sync_players):
        """Test background sync function logs results."""
        from hooptipp.nba.admin import _run_player_sync_background
        
        mock_sync_players.return_value = SyncResult(created=10, updated=20, removed=5)
        
        _run_player_sync_background()
        
        # Verify sync was called
        mock_sync_players.assert_called_once()
        
        # Verify logging
        mock_logger.info.assert_called()
        log_calls = [str(call) for call in mock_logger.info.call_args_list]
        log_text = ' '.join(log_calls)
        self.assertIn('10 player(s) created', log_text)
        self.assertIn('20 player(s) updated', log_text)
        self.assertIn('5 player(s) removed', log_text)

    @patch('hooptipp.nba.admin.sync_players_from_hoopshype')
    @patch('hooptipp.nba.admin.logger')
    def test_background_sync_logs_errors(self, mock_logger, mock_sync_players):
        """Test background sync function logs errors."""
        from hooptipp.nba.admin import _run_player_sync_background
        
        mock_sync_players.side_effect = Exception('API failed')
        
        _run_player_sync_background()
        
        # Verify error was logged
        mock_logger.exception.assert_called_once()
        log_call = str(mock_logger.exception.call_args)
        self.assertIn('API failed', log_call)
