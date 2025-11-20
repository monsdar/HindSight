"""Tests for DBB admin views."""

from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User, Permission
from django.test import TestCase, Client
from django.urls import reverse

from hooptipp.dbb.models import TrackedLeague, TrackedTeam


class DbbAdminViewsTest(TestCase):
    """Tests for DBB admin views."""

    def setUp(self):
        """Set up test user with permissions."""
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='password'
        )
        self.client.force_login(self.user)

    @patch('hooptipp.dbb.admin.build_slapi_client')
    def test_select_verband_view(self, mock_build_client):
        """Test verband selection view."""
        mock_client = MagicMock()
        mock_client.get_verbaende.return_value = [
            {'id': '100', 'label': 'Bundesligen', 'hits': 34},
            {'id': '101', 'label': 'Landesverbände', 'hits': 22}
        ]
        mock_build_client.return_value = mock_client

        response = self.client.get(reverse('admin:dbb_select_verband'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bundesligen')
        self.assertContains(response, 'Landesverbände')
        self.assertContains(response, 'Search Clubs')

    @patch('hooptipp.dbb.admin.build_slapi_client')
    def test_select_verband_view_empty_list(self, mock_build_client):
        """Test verband selection view with empty list."""
        mock_client = MagicMock()
        mock_client.get_verbaende.return_value = []
        mock_build_client.return_value = mock_client

        response = self.client.get(reverse('admin:dbb_select_verband'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No Verbände found')

    @patch('hooptipp.dbb.admin.build_slapi_client')
    def test_select_verband_view_with_wrapped_response(self, mock_build_client):
        """Test that wrapped API responses work correctly."""
        mock_client = MagicMock()
        # Simulate what happens when client normalizes wrapped response
        mock_client.get_verbaende.return_value = [
            {'id': '100', 'label': 'Bundesligen', 'hits': 34}
        ]
        mock_build_client.return_value = mock_client

        response = self.client.get(reverse('admin:dbb_select_verband'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bundesligen')
        self.assertContains(response, '100')

    @patch('hooptipp.dbb.admin.build_slapi_client')
    def test_search_clubs_view(self, mock_build_client):
        """Test club search view returns leagues."""
        mock_client = MagicMock()
        mock_client.get_club_leagues.return_value = [
            {'liga_id': 48693, 'liganame': 'Regionsliga Süd Herren'},
            {'liga_id': 48694, 'liganame': 'Regionsliga Mixed'}
        ]
        mock_client.get_league_standings.return_value = [
            {'position': 1, 'team': {'id': 't1', 'name': 'BG Test Team 1'}},
            {'position': 2, 'team': {'id': 't2', 'name': 'BG Test Team 2'}}
        ]
        mock_build_client.return_value = mock_client

        url = reverse('admin:dbb_search_clubs')
        response = self.client.get(url, {
            'verband_id': '7',
            'verband_name': 'Test Verband',
            'query': 'Test'
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Regionsliga Süd Herren')
        self.assertContains(response, 'BG Test Team 1')


    def test_import_leagues_view(self):
        """Test importing leagues and teams."""
        url = reverse('admin:dbb_import_leagues')
        response = self.client.post(url, {
            'verband_id': 'v1',
            'verband_name': 'Test Verband',
            'club_search_term': 'Test Club',
            'league_l1': 'League 1',
            'team_l1_1': '{"name": "Team 1", "id": "t1"}',
            'team_l1_2': '{"name": "Team 2", "id": "t2"}',
        })

        # Should redirect to tracked leagues list
        self.assertEqual(response.status_code, 302)

        # Check that league and teams were created
        self.assertTrue(TrackedLeague.objects.filter(league_id='l1').exists())
        league = TrackedLeague.objects.get(league_id='l1')
        self.assertEqual(league.teams.count(), 2)
        self.assertTrue(league.teams.filter(team_name='Team 1').exists())
        self.assertTrue(league.teams.filter(team_name='Team 2').exists())

    def test_admin_without_permission(self):
        """Test that admin views require permissions."""
        # Create user without permissions
        user = User.objects.create_user(
            username='user',
            password='password'
        )
        client = Client()
        client.force_login(user)

        # Try to access select verband view - should get PermissionDenied or redirect
        response = client.get(reverse('admin:dbb_select_verband'))
        # Django admin redirects to login or returns 403
        self.assertIn(response.status_code, [302, 403])


class TrackedLeagueAdminTest(TestCase):
    """Tests for TrackedLeague admin."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='password'
        )
        self.client.force_login(self.user)

        self.league = TrackedLeague.objects.create(
            verband_name='Test Verband',
            verband_id='v1',
            league_name='Test League',
            league_id='l1',
            club_search_term='Test Club'
        )

    def test_tracked_league_list_display(self):
        """Test that tracked league list displays correctly."""
        url = reverse('admin:dbb_trackedleague_changelist')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test League')
        self.assertContains(response, 'Test Verband')

    def test_tracked_league_detail(self):
        """Test viewing tracked league details."""
        url = reverse('admin:dbb_trackedleague_change', args=[self.league.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test League')
        self.assertContains(response, 'Test Verband')

