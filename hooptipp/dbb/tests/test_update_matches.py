"""Tests for update_dbb_matches management command."""

from io import StringIO
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from hooptipp.dbb.models import TrackedLeague, TrackedTeam


class UpdateDbbMatchesCommandTest(TestCase):
    """Tests for update_dbb_matches command."""

    def setUp(self):
        """Set up test data."""
        self.league = TrackedLeague.objects.create(
            verband_name='Test Verband',
            verband_id='v1',
            league_name='Test League',
            league_id='l1',
            club_search_term='Test Club',
            is_active=True
        )
        
        self.team = TrackedTeam.objects.create(
            tracked_league=self.league,
            team_name='BG Test Team',
            team_id='t1',
            is_active=True
        )

    @patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client')
    def test_command_without_api_token(self, mock_build_client):
        """Test command fails gracefully without API token."""
        mock_build_client.return_value = None
        
        out = StringIO()
        call_command('update_dbb_matches', stdout=out)
        
        output = out.getvalue()
        self.assertIn('SLAPI is not configured', output)

    @patch('hooptipp.dbb.management.commands.update_dbb_matches.DbbEventSource')
    @patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client')
    def test_command_with_dry_run(self, mock_build_client, mock_event_source_class):
        """Test command with dry-run flag."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        out = StringIO()
        call_command('update_dbb_matches', '--dry-run', stdout=out)
        
        output = out.getvalue()
        self.assertIn('DRY RUN MODE', output)

    @patch('hooptipp.dbb.management.commands.update_dbb_matches.DbbEventSource')
    @patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client')
    def test_command_syncs_matches(self, mock_build_client, mock_event_source_class):
        """Test command syncs matches successfully."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Mock event source
        mock_event_source = MagicMock()
        mock_event_source_class.return_value = mock_event_source
        
        # Mock sync results
        from hooptipp.predictions.event_sources.base import EventSourceResult
        options_result = EventSourceResult()
        options_result.options_created = 2
        events_result = EventSourceResult()
        events_result.events_created = 5
        
        mock_event_source.sync_options.return_value = options_result
        mock_event_source.sync_events.return_value = events_result
        
        out = StringIO()
        call_command('update_dbb_matches', stdout=out)
        
        output = out.getvalue()
        self.assertIn('Match update completed', output)
        
        # Verify event source methods were called
        mock_event_source.sync_options.assert_called_once()
        mock_event_source.sync_events.assert_called_once()

    @patch('hooptipp.dbb.management.commands.update_dbb_matches.DbbEventSource')
    @patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client')
    def test_command_with_specific_league(self, mock_build_client, mock_event_source_class):
        """Test command with specific league ID."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        mock_event_source = MagicMock()
        mock_event_source_class.return_value = mock_event_source
        
        from hooptipp.predictions.event_sources.base import EventSourceResult
        mock_event_source.sync_options.return_value = EventSourceResult()
        mock_event_source.sync_events.return_value = EventSourceResult()
        
        out = StringIO()
        call_command('update_dbb_matches', '--league-id', 'l1', stdout=out)
        
        output = out.getvalue()
        self.assertIn('Match update completed', output)

    def test_command_with_no_tracked_leagues(self):
        """Test command when no tracked leagues exist."""
        # Delete the league we created in setUp
        self.league.delete()
        
        out = StringIO()
        
        # Mock the client so it doesn't fail on API token check
        with patch('hooptipp.dbb.management.commands.update_dbb_matches.build_slapi_client') as mock_build:
            mock_build.return_value = MagicMock()
            call_command('update_dbb_matches', stdout=out)
        
        output = out.getvalue()
        self.assertIn('No active tracked leagues', output)

