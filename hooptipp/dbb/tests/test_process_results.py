"""Tests for process_dbb_results management command."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from hooptipp.predictions.models import (
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
    UserTip,
)
from hooptipp.dbb.models import DbbMatch


class ProcessDbbResultsCommandTest(TestCase):
    """Tests for process_dbb_results command."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            password='password'
        )
        
        # Create tip type
        self.tip_type = TipType.objects.create(
            name='DBB Matches',
            slug='dbb-matches',
            category=TipType.TipCategory.GAME,
            deadline=timezone.now()
        )
        
        # Create option category and teams
        self.category = OptionCategory.objects.create(
            slug='dbb-teams',
            name='German Basketball Teams'
        )
        
        self.team1 = Option.objects.create(
            category=self.category,
            slug='team-1',
            name='Team 1'
        )
        
        self.team2 = Option.objects.create(
            category=self.category,
            slug='team-2',
            name='Team 2'
        )
        
        # Create past prediction event
        past_time = timezone.now() - timedelta(hours=3)
        self.event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Team 1 @ Team 2',
            source_id='dbb-slapi',
            source_event_id='123',  # match_id as string
            metadata={'league_id': 'test_league_123'},  # Add league_id for fetching matches
            opens_at=past_time - timedelta(days=7),
            deadline=past_time,
            reveal_at=past_time - timedelta(days=7),
            is_active=True
        )
        
        # Create prediction options
        self.option1 = PredictionOption.objects.create(
            event=self.event,
            option=self.team1,
            label='Team 1',
            sort_order=1,
            is_active=True
        )
        
        self.option2 = PredictionOption.objects.create(
            event=self.event,
            option=self.team2,
            label='Team 2',
            sort_order=2,
            is_active=True
        )
        
        # Create user tip
        UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.option1,
            selected_option=self.team1,
            prediction='Team 1'
        )

    @patch('hooptipp.dbb.management.commands.process_dbb_results.build_slapi_client')
    def test_command_without_api_token(self, mock_build_client):
        """Test command fails gracefully without API token."""
        mock_build_client.return_value = None
        
        out = StringIO()
        call_command('process_dbb_results', stdout=out)
        
        output = out.getvalue()
        self.assertIn('SLAPI is not configured', output)

    @patch('hooptipp.dbb.management.commands.process_dbb_results.build_slapi_client')
    def test_command_with_dry_run(self, mock_build_client):
        """Test command with dry-run flag."""
        mock_client = MagicMock()
        # Mock get_league_matches to return match with score string
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 123,
                'home_team': {'name': 'Team 2'},
                'away_team': {'name': 'Team 1'},
                'score': '78:85',  # away:home format
                'is_finished': True,
                'is_cancelled': False
            }
        ]
        mock_build_client.return_value = mock_client
        
        out = StringIO()
        call_command('process_dbb_results', '--dry-run', stdout=out)
        
        output = out.getvalue()
        self.assertIn('Would create outcome', output)

    @patch('hooptipp.dbb.management.commands.process_dbb_results.build_slapi_client')
    def test_command_processes_finished_match(self, mock_build_client):
        """Test command processes finished match."""
        mock_client = MagicMock()
        # Mock get_league_matches to return match with score string
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 123,
                'home_team': {'name': 'Team 2'},
                'away_team': {'name': 'Team 1'},
                'score': '78:85',  # away:home format (Team 2 wins 85-78)
                'is_finished': True,
                'is_cancelled': False
            }
        ]
        mock_build_client.return_value = mock_client
        
        out = StringIO()
        call_command('process_dbb_results', stdout=out)
        
        output = out.getvalue()
        self.assertIn('Processed:', output)
        
        # Verify outcome was created
        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.outcome)
        self.assertEqual(self.event.outcome.winning_option, self.option2)  # Team 2 wins

    @patch('hooptipp.dbb.management.commands.process_dbb_results.build_slapi_client')
    def test_command_skips_unfinished_match(self, mock_build_client):
        """Test command skips unfinished matches."""
        mock_client = MagicMock()
        # Mock get_league_matches to return unfinished match
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 123,
                'home_team': {'name': 'Team 2'},
                'away_team': {'name': 'Team 1'},
                'is_finished': False,
                'is_cancelled': False
            }
        ]
        mock_build_client.return_value = mock_client
        
        out = StringIO()
        call_command('process_dbb_results', stdout=out)
        
        output = out.getvalue()
        self.assertIn('Skipped:', output)
        
        # Verify outcome was not created
        self.event.refresh_from_db()
        self.assertFalse(hasattr(self.event, 'outcome'))

    @patch('hooptipp.dbb.management.commands.process_dbb_results.build_slapi_client')
    def test_command_with_hours_back_parameter(self, mock_build_client):
        """Test command with custom hours-back parameter."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        out = StringIO()
        call_command('process_dbb_results', '--hours-back', '48', stdout=out)
        
        output = out.getvalue()
        # Should complete without error
        self.assertIn('Completed:', output)

    def test_command_with_no_events_to_process(self):
        """Test command when no events need processing."""
        # Delete the event we created
        self.event.delete()
        
        out = StringIO()
        
        with patch('hooptipp.dbb.management.commands.process_dbb_results.build_slapi_client') as mock_build:
            mock_build.return_value = MagicMock()
            call_command('process_dbb_results', stdout=out)
        
        output = out.getvalue()
        self.assertIn('No events found', output)

    @patch('hooptipp.dbb.management.commands.process_dbb_results.build_slapi_client')
    def test_command_handles_api_errors(self, mock_build_client):
        """Test command handles API errors gracefully."""
        mock_client = MagicMock()
        mock_client.get_league_matches.side_effect = Exception('API Error')
        mock_build_client.return_value = mock_client
        
        out = StringIO()
        call_command('process_dbb_results', stdout=out)
        
        output = out.getvalue()
        self.assertIn('Skipped:', output)

