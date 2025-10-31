"""
Tests for the process_game_outcomes management command.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from django.contrib.auth import get_user_model

from hooptipp.predictions.models import (
    EventOutcome, Option, OptionCategory, PredictionEvent, 
    PredictionOption, TipType, UserTip
)
from hooptipp.nba.models import ScheduledGame

User = get_user_model()


class ProcessGameOutcomesCommandTest(TestCase):
    """Test the process_game_outcomes management command."""

    def setUp(self):
        """Set up test data."""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create option category and teams
        self.teams_cat = OptionCategory.objects.create(
            slug='nba-teams',
            name='NBA Teams',
            description='NBA team options'
        )
        
        self.home_team = Option.objects.create(
            category=self.teams_cat,
            slug='lakers',
            name='Los Angeles Lakers',
            short_name='LAL',
            external_id='14'
        )
        
        self.away_team = Option.objects.create(
            category=self.teams_cat,
            slug='warriors',
            name='Golden State Warriors',
            short_name='GSW',
            external_id='10'
        )
        
        # Create tip type
        self.tip_type = TipType.objects.create(
            name='Test Games',
            slug='test-games',
            description='Test tip type',
            deadline=timezone.now() + timedelta(hours=1)
        )
        
        # Create scheduled game
        self.scheduled_game = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id='12345',
            game_date=timezone.now() - timedelta(hours=2),
            home_team='Los Angeles Lakers',
            home_team_tricode='LAL',
            away_team='Golden State Warriors',
            away_team_tricode='GSW',
            venue='Crypto.com Arena'
        )
        
        # Create prediction event
        self.prediction_event = PredictionEvent.objects.create(
            scheduled_game=self.scheduled_game,
            tip_type=self.tip_type,
            name='GSW @ LAL',
            description='Golden State Warriors at Los Angeles Lakers',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='nba-balldontlie',
            source_event_id='12345',
            opens_at=timezone.now() - timedelta(hours=3),
            deadline=timezone.now() - timedelta(hours=2),
            reveal_at=timezone.now() - timedelta(hours=3),
            is_active=True,
            points=1
        )
        
        # Create prediction options
        self.home_option = PredictionOption.objects.create(
            event=self.prediction_event,
            option=self.home_team,
            label='Los Angeles Lakers',
            sort_order=1,
            is_active=True
        )
        
        self.away_option = PredictionOption.objects.create(
            event=self.prediction_event,
            option=self.away_team,
            label='Golden State Warriors',
            sort_order=2,
            is_active=True
        )
    
    def _mock_batch_fetch_game_data(self, game_data_dict: dict):
        """
        Helper method to mock batch_fetch_game_data.
        
        Args:
            game_data_dict: Dictionary mapping game_id to game data dict
        """
        def mock_batch_fetch(events):
            return game_data_dict
        return patch(
            'hooptipp.nba.management.commands.process_game_outcomes.Command.batch_fetch_game_data',
            side_effect=mock_batch_fetch
        )
    
    def _create_mock_game_response(self, game_id: str, home_score: int, away_score: int, status: str = 'Final'):
        """Helper to create a mock game object from the API response."""
        mock_game = MagicMock()
        mock_game.id = int(game_id)
        mock_game.home_team_score = home_score
        mock_game.visitor_team_score = away_score
        mock_game.status = status
        return mock_game
    
    def _mock_build_client_with_games(self, game_data_dict: dict):
        """
        Helper to mock _build_bdl_client with games.list() response.
        
        Args:
            game_data_dict: Dictionary mapping game_id to game data dict
        """
        # Create mock game objects
        mock_games = []
        for game_id, data in game_data_dict.items():
            mock_game = self._create_mock_game_response(
                game_id,
                data.get('home_score', 0),
                data.get('away_score', 0),
                data.get('game_status', 'Final')
            )
            mock_games.append(mock_game)
        
        # Create mock response
        mock_response = MagicMock()
        mock_response.data = mock_games
        mock_response.meta = MagicMock()
        mock_response.meta.next_cursor = None
        
        # Create mock client
        mock_client = MagicMock()
        mock_client.nba.games.list.return_value = mock_response
        
        return patch(
            'hooptipp.nba.management.commands.process_game_outcomes._build_bdl_client',
            return_value=mock_client
        )

    def test_command_help(self):
        """Test that the command help is displayed correctly."""
        with self.assertRaises(SystemExit):
            call_command('process_game_outcomes', '--help')

    def test_dry_run_mode(self):
        """Test dry run mode shows what would be processed."""
        game_data = {
            '12345': {
                'game_status': 'Final',
                'home_score': 110,
                'away_score': 105,
                'is_live': False
            }
        }
        with self._mock_build_client_with_games(game_data):
            # Capture output
            from io import StringIO
            out = StringIO()
            
            call_command('process_game_outcomes', '--dry-run', stdout=out)
            
            output = out.getvalue()
            self.assertIn('Would create outcome', output)
            self.assertIn('GSW @ LAL', output)
            self.assertIn('Los Angeles Lakers', output)
            
            # Verify no EventOutcome was created
            self.assertEqual(EventOutcome.objects.count(), 0)

    def test_process_final_game_home_winner(self):
        """Test processing a final game with home team winner."""
        game_data = {
            '12345': {
                'game_status': 'Final',
                'home_score': 110,
                'away_score': 105,
                'is_live': False
            }
        }
        with self._mock_build_client_with_games(game_data):
            call_command('process_game_outcomes')
            
            # Verify EventOutcome was created
            self.assertEqual(EventOutcome.objects.count(), 1)
            outcome = EventOutcome.objects.first()
            self.assertEqual(outcome.prediction_event, self.prediction_event)
            self.assertEqual(outcome.winning_option, self.home_option)
            self.assertEqual(outcome.winning_generic_option, self.home_team)
            self.assertIn('Final score: GSW 105, LAL 110', outcome.notes)
            
            # Verify metadata was stored correctly
            self.assertIsNotNone(outcome.metadata)
            self.assertEqual(outcome.metadata['away_score'], 105)
            self.assertEqual(outcome.metadata['home_score'], 110)
            self.assertEqual(outcome.metadata['away_team'], 'GSW')
            self.assertEqual(outcome.metadata['home_team'], 'LAL')
            self.assertEqual(outcome.metadata['away_team_full'], 'Golden State Warriors')
            self.assertEqual(outcome.metadata['home_team_full'], 'Los Angeles Lakers')
            self.assertEqual(outcome.metadata['game_status'], 'Final')
            self.assertEqual(outcome.metadata['nba_game_id'], '12345')

    def test_process_final_game_away_winner(self):
        """Test processing a final game with away team winner."""
        # Clear any existing outcomes first
        EventOutcome.objects.all().delete()
        
        game_data = {
            '12345': {
                'game_status': 'Final',
                'home_score': 105,
                'away_score': 110,
                'is_live': False
            }
        }
        with self._mock_build_client_with_games(game_data):
            call_command('process_game_outcomes')
            
            # Verify EventOutcome was created
            self.assertEqual(EventOutcome.objects.count(), 1)
            outcome = EventOutcome.objects.first()
            self.assertEqual(outcome.prediction_event, self.prediction_event)
            self.assertEqual(outcome.winning_option, self.away_option)
            self.assertEqual(outcome.winning_generic_option, self.away_team)

    def test_skip_non_final_game(self):
        """Test that non-final games are skipped."""
        # Clear any existing outcomes first
        EventOutcome.objects.all().delete()
        
        game_data = {
            '12345': {
                'game_status': 'Q3 5:23',
                'home_score': 80,
                'away_score': 75,
                'is_live': True
            }
        }
        with self._mock_build_client_with_games(game_data):
            call_command('process_game_outcomes')
            
            # Verify no EventOutcome was created
            self.assertEqual(EventOutcome.objects.count(), 0)

    def test_skip_tied_game(self):
        """Test that tied games are skipped."""
        # Clear any existing outcomes first
        EventOutcome.objects.all().delete()
        
        game_data = {
            '12345': {
                'game_status': 'Final',
                'home_score': 105,
                'away_score': 105,
                'is_live': False
            }
        }
        with self._mock_build_client_with_games(game_data):
            call_command('process_game_outcomes')
            
            # Verify no EventOutcome was created
            self.assertEqual(EventOutcome.objects.count(), 0)

    def test_skip_missing_scores(self):
        """Test that games with missing scores are skipped."""
        # Clear any existing outcomes first
        EventOutcome.objects.all().delete()
        
        # Create a mock game with missing score
        mock_game = self._create_mock_game_response('12345', None, 105, 'Final')
        mock_game.home_team_score = None
        
        mock_response = MagicMock()
        mock_response.data = [mock_game]
        mock_response.meta = MagicMock()
        mock_response.meta.next_cursor = None
        
        mock_client = MagicMock()
        mock_client.nba.games.list.return_value = mock_response
        
        with patch(
            'hooptipp.nba.management.commands.process_game_outcomes._build_bdl_client',
            return_value=mock_client
        ):
            call_command('process_game_outcomes')
            
            # Verify no EventOutcome was created
            self.assertEqual(EventOutcome.objects.count(), 0)

    def test_skip_missing_prediction_option(self):
        """Test that games with missing prediction options are skipped."""
        # Clear any existing outcomes first
        EventOutcome.objects.all().delete()
        
        # Remove the home team option
        self.home_option.delete()
        
        game_data = {
            '12345': {
                'game_status': 'Final',
                'home_score': 110,
                'away_score': 105,
                'is_live': False
            }
        }
        with self._mock_build_client_with_games(game_data):
            call_command('process_game_outcomes')
            
            # Verify no EventOutcome was created
            self.assertEqual(EventOutcome.objects.count(), 0)

    def test_skip_already_processed_event(self):
        """Test that events with existing outcomes are skipped."""
        # Create existing outcome
        EventOutcome.objects.create(
            prediction_event=self.prediction_event,
            winning_option=self.home_option,
            winning_generic_option=self.home_team,
            resolved_at=timezone.now()
        )
        
        game_data = {
            '12345': {
                'game_status': 'Final',
                'home_score': 110,
                'away_score': 105,
                'is_live': False
            }
        }
        with self._mock_build_client_with_games(game_data):
            call_command('process_game_outcomes')
            
            # Verify only one EventOutcome exists (the original one)
            self.assertEqual(EventOutcome.objects.count(), 1)

    def test_hours_back_parameter(self):
        """Test the hours-back parameter."""
        # Create an older event that should be processed with 48 hours back
        old_game = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id='99999',
            game_date=timezone.now() - timedelta(hours=36),  # Within 48 hours
            home_team='Old Team',
            home_team_tricode='OLD',
            away_team='Older Team',
            away_team_tricode='OLD2',
            venue='Old Arena'
        )
        
        old_event = PredictionEvent.objects.create(
            scheduled_game=old_game,
            tip_type=self.tip_type,
            name='OLD @ OLD2',
            description='Old game',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='nba-balldontlie',
            source_event_id='99999',
            opens_at=timezone.now() - timedelta(hours=37),
            deadline=timezone.now() - timedelta(hours=36),  # Within 48 hours
            reveal_at=timezone.now() - timedelta(hours=37),
            is_active=True,
            points=1
        )
        
        # Create options for the old event
        old_home_team = Option.objects.create(
            category=self.teams_cat,
            slug='old-team',
            name='Old Team',
            short_name='OLD',
            external_id='999'
        )
        
        old_away_team = Option.objects.create(
            category=self.teams_cat,
            slug='older-team',
            name='Older Team',
            short_name='OLD2',
            external_id='998'
        )
        
        PredictionOption.objects.create(
            event=old_event,
            option=old_home_team,
            label='Old Team',
            sort_order=1,
            is_active=True
        )
        
        PredictionOption.objects.create(
            event=old_event,
            option=old_away_team,
            label='Older Team',
            sort_order=2,
            is_active=True
        )
        
        game_data_all = {
            '12345': {
                'game_status': 'Final',
                'home_score': 110,
                'away_score': 105,
                'is_live': False
            },
            '99999': {
                'game_status': 'Final',
                'home_score': 100,
                'away_score': 95,
                'is_live': False
            }
        }
        with self._mock_build_client_with_games(game_data_all):
            # Run with default hours-back (24)
            call_command('process_game_outcomes')
            
            # Should only process the recent event
            self.assertEqual(EventOutcome.objects.count(), 1)
            self.assertEqual(EventOutcome.objects.first().prediction_event, self.prediction_event)
            
            # Clear the outcome
            EventOutcome.objects.all().delete()
            
            # Run with 48 hours back
            call_command('process_game_outcomes', '--hours-back', '48')
            
            # Should process both events
            self.assertEqual(EventOutcome.objects.count(), 2)

    def test_automation_disabled_environment_variable(self):
        """Test that automation can be disabled via environment variable."""
        game_data = {
            '12345': {
                'game_status': 'Final',
                'home_score': 110,
                'away_score': 105,
                'is_live': False
            }
        }
        with patch.dict(os.environ, {'AUTO_PROCESS_GAME_OUTCOMES': 'false'}):
            with self._mock_build_client_with_games(game_data):
                call_command('process_game_outcomes')
                
                # Verify no EventOutcome was created
                self.assertEqual(EventOutcome.objects.count(), 0)

    def test_force_override_environment_variable(self):
        """Test that --force can override the environment variable."""
        game_data = {
            '12345': {
                'game_status': 'Final',
                'home_score': 110,
                'away_score': 105,
                'is_live': False
            }
        }
        with patch.dict(os.environ, {'AUTO_PROCESS_GAME_OUTCOMES': 'false'}):
            with self._mock_build_client_with_games(game_data):
                call_command('process_game_outcomes', '--force')
                
                # Verify EventOutcome was created despite disabled automation
                self.assertEqual(EventOutcome.objects.count(), 1)

    def test_environment_variable_hours_back(self):
        """Test that hours-back can be set via environment variable."""
        game_data = {
            '12345': {
                'game_status': 'Final',
                'home_score': 110,
                'away_score': 105,
                'is_live': False
            }
        }
        with patch.dict(os.environ, {'GAME_OUTCOME_PROCESSING_HOURS_BACK': '48'}):
            with self._mock_build_client_with_games(game_data):
                # This should use the environment variable value
                call_command('process_game_outcomes')
                
                # Verify EventOutcome was created
                self.assertEqual(EventOutcome.objects.count(), 1)

    def test_auto_scoring_integration(self):
        """Test that the command automatically scores events after creating outcomes."""
        # Create a user tip
        UserTip.objects.create(
            user=self.user,
            tip_type=self.tip_type,
            prediction_event=self.prediction_event,
            prediction_option=self.home_option,
            selected_option=self.home_team,
            prediction='Los Angeles Lakers will win',
            is_locked=False
        )
        
        game_data = {
            '12345': {
                'game_status': 'Final',
                'home_score': 110,
                'away_score': 105,
                'is_live': False
            }
        }
        with self._mock_build_client_with_games(game_data):
            call_command('process_game_outcomes')
            
            # Verify EventOutcome was created and scored
            self.assertEqual(EventOutcome.objects.count(), 1)
            outcome = EventOutcome.objects.first()
            self.assertIsNotNone(outcome.scored_at)

    def test_error_handling(self):
        """Test that errors are handled gracefully."""
        # Clear any existing outcomes first
        EventOutcome.objects.all().delete()
        
        with patch(
            'hooptipp.nba.management.commands.process_game_outcomes._build_bdl_client',
            side_effect=Exception('API Error')
        ):
            # Should not raise an exception
            call_command('process_game_outcomes')
            
            # Verify no EventOutcome was created
            self.assertEqual(EventOutcome.objects.count(), 0)

    def test_multiple_events_processing(self):
        """Test processing multiple events."""
        # Create another event
        game2 = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id='54321',
            game_date=timezone.now() - timedelta(hours=1),
            home_team='Boston Celtics',
            home_team_tricode='BOS',
            away_team='Miami Heat',
            away_team_tricode='MIA',
            venue='TD Garden'
        )
        
        event2 = PredictionEvent.objects.create(
            scheduled_game=game2,
            tip_type=self.tip_type,
            name='MIA @ BOS',
            description='Miami Heat at Boston Celtics',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='nba-balldontlie',
            source_event_id='54321',
            opens_at=timezone.now() - timedelta(hours=2),
            deadline=timezone.now() - timedelta(hours=1),
            reveal_at=timezone.now() - timedelta(hours=2),
            is_active=True,
            points=1
        )
        
        # Create options for the second event
        # Create Boston Celtics option
        boston_team = Option.objects.create(
            category=self.teams_cat,
            slug='celtics',
            name='Boston Celtics',
            short_name='BOS',
            external_id='2'
        )
        
        PredictionOption.objects.create(
            event=event2,
            option=boston_team,
            label='Boston Celtics',
            sort_order=1,
            is_active=True
        )
        
        # Create Miami Heat option
        miami_team = Option.objects.create(
            category=self.teams_cat,
            slug='heat',
            name='Miami Heat',
            short_name='MIA',
            external_id='16'
        )
        
        PredictionOption.objects.create(
            event=event2,
            option=miami_team,
            label='Miami Heat',
            sort_order=2,
            is_active=True
        )
        
        game_data_multi = {
            '12345': {
                'game_status': 'Final',
                'home_score': 110,
                'away_score': 105,
                'is_live': False
            },
            '54321': {
                'game_status': 'Final',
                'home_score': 100,
                'away_score': 95,
                'is_live': False
            }
        }
        with self._mock_build_client_with_games(game_data_multi):
            call_command('process_game_outcomes')
            
            # Verify both EventOutcomes were created
            self.assertEqual(EventOutcome.objects.count(), 2)
