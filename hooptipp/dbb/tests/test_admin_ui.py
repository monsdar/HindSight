"""Tests for DBB admin UI elements."""

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse


class DbbAdminUITest(TestCase):
    """Tests for DBB admin UI customizations."""

    def setUp(self):
        """Set up test user with permissions."""
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='password'
        )
        self.client.force_login(self.user)

    def test_tracked_league_changelist_has_custom_button(self):
        """Test that the TrackedLeague changelist has the custom import button."""
        url = reverse('admin:dbb_trackedleague_changelist')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Check for the custom button link
        self.assertContains(response, 'Add Leagues from Verband')
        self.assertContains(response, reverse('admin:dbb_select_verband'))

    def test_sync_matches_action_available(self):
        """Test that the sync matches action is available in the admin."""
        from hooptipp.dbb.models import TrackedLeague
        
        # Create a tracked league so the actions dropdown appears
        TrackedLeague.objects.create(
            verband_name='Test Verband',
            verband_id='v1',
            league_name='Test League',
            league_id='l1',
            club_search_term='Test'
        )
        
        url = reverse('admin:dbb_trackedleague_changelist')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Check that the action is in the actions dropdown
        # Django renders it with the description text
        self.assertContains(response, 'Sync matches for selected leagues')

