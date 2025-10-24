"""
Tests for the backfill_eventoutcome_metadata management command.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from django.contrib.auth import get_user_model

from hooptipp.predictions.models import (
    EventOutcome, Option, OptionCategory, PredictionEvent, 
    PredictionOption, TipType
)
from hooptipp.nba.models import ScheduledGame

User = get_user_model()


class BackfillEventOutcomeMetadataCommandTest(TestCase):
    """Test the backfill_eventoutcome_metadata management command."""

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
        
        # Create EventOutcome without metadata
        self.event_outcome = EventOutcome.objects.create(
            prediction_event=self.prediction_event,
            winning_option=self.home_option,
            winning_generic_option=self.home_team,
            resolved_at=timezone.now(),
            notes='Test outcome',
            metadata={}  # Explicitly set empty metadata
        )

    def test_command_help(self):
        """Test that the command help is displayed correctly."""
        with self.assertRaises(SystemExit):
            call_command('backfill_eventoutcome_metadata', '--help')

    def test_dry_run_mode(self):
        """Test dry run mode shows what would be updated."""
        with patch('hooptipp.nba.management.commands.backfill_eventoutcome_metadata.Command.batch_fetch_game_data') as mock_batch_fetch:
            mock_batch_fetch.return_value = {
                '12345': {
                    'game_status': 'Final',
                    'home_score': 110,
                    'away_score': 105,
                    'is_live': False
                }
            }
            
            # Capture output
            from io import StringIO
            out = StringIO()
            
            call_command('backfill_eventoutcome_metadata', '--dry-run', stdout=out)
            
            output = out.getvalue()
            self.assertIn('Would update metadata', output)
            self.assertIn('GSW @ LAL', output)
            self.assertIn('Final: GSW 105, LAL 110', output)
            
            # Verify metadata was not updated
            self.event_outcome.refresh_from_db()
            self.assertEqual(self.event_outcome.metadata, {})

    def test_update_eventoutcome_metadata(self):
        """Test updating EventOutcome metadata with live data."""
        with patch('hooptipp.nba.management.commands.backfill_eventoutcome_metadata.Command.batch_fetch_game_data') as mock_batch_fetch:
            mock_batch_fetch.return_value = {
                '12345': {
                    'game_status': 'Final',
                    'home_score': 110,
                    'away_score': 105,
                    'is_live': False
                }
            }
            
            call_command('backfill_eventoutcome_metadata')
            
            # Verify metadata was updated
            self.event_outcome.refresh_from_db()
            self.assertIsNotNone(self.event_outcome.metadata)
            self.assertEqual(self.event_outcome.metadata['away_score'], 105)
            self.assertEqual(self.event_outcome.metadata['home_score'], 110)
            self.assertEqual(self.event_outcome.metadata['away_team'], 'GSW')
            self.assertEqual(self.event_outcome.metadata['home_team'], 'LAL')
            self.assertEqual(self.event_outcome.metadata['away_team_full'], 'Golden State Warriors')
            self.assertEqual(self.event_outcome.metadata['home_team_full'], 'Los Angeles Lakers')
            self.assertEqual(self.event_outcome.metadata['game_status'], 'Final')
            self.assertEqual(self.event_outcome.metadata['nba_game_id'], '12345')

    def test_skip_eventoutcome_with_existing_metadata(self):
        """Test that EventOutcomes with existing metadata are skipped by default."""
        # Add existing metadata
        self.event_outcome.metadata = {'existing': 'data'}
        self.event_outcome.save()
        
        with patch('hooptipp.nba.management.commands.backfill_eventoutcome_metadata.Command.batch_fetch_game_data') as mock_batch_fetch:
            mock_batch_fetch.return_value = {
                '12345': {
                    'game_status': 'Final',
                    'home_score': 110,
                    'away_score': 105,
                    'is_live': False
                }
            }
            
            call_command('backfill_eventoutcome_metadata')
            
            # Verify metadata was not updated
            self.event_outcome.refresh_from_db()
            self.assertEqual(self.event_outcome.metadata, {'existing': 'data'})

    def test_force_update_eventoutcome_with_existing_metadata(self):
        """Test that --force can update EventOutcomes with existing metadata."""
        # Add existing metadata
        self.event_outcome.metadata = {'existing': 'data'}
        self.event_outcome.save()
        
        with patch('hooptipp.nba.management.commands.backfill_eventoutcome_metadata.Command.batch_fetch_game_data') as mock_batch_fetch:
            mock_batch_fetch.return_value = {
                '12345': {
                    'game_status': 'Final',
                    'home_score': 110,
                    'away_score': 105,
                    'is_live': False
                }
            }
            
            call_command('backfill_eventoutcome_metadata', '--force')
            
            # Verify metadata was updated
            self.event_outcome.refresh_from_db()
            self.assertEqual(self.event_outcome.metadata['away_score'], 105)
            self.assertEqual(self.event_outcome.metadata['home_score'], 110)
            self.assertEqual(self.event_outcome.metadata['away_team'], 'GSW')
            self.assertEqual(self.event_outcome.metadata['home_team'], 'LAL')

    def test_skip_eventoutcome_without_live_data(self):
        """Test that EventOutcomes without live data are skipped."""
        with patch('hooptipp.nba.management.commands.backfill_eventoutcome_metadata.Command.batch_fetch_game_data') as mock_batch_fetch:
            mock_batch_fetch.return_value = {}  # No game data available
            
            call_command('backfill_eventoutcome_metadata')
            
            # Verify metadata was not updated
            self.event_outcome.refresh_from_db()
            self.assertEqual(self.event_outcome.metadata, {})

    def test_limit_parameter(self):
        """Test the limit parameter."""
        # Create another EventOutcome
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
        
        PredictionOption.objects.create(
            event=event2,
            option=self.home_team,
            label='Boston Celtics',
            sort_order=1,
            is_active=True
        )
        
        EventOutcome.objects.create(
            prediction_event=event2,
            winning_option=self.home_option,
            winning_generic_option=self.home_team,
            resolved_at=timezone.now(),
            notes='Test outcome 2'
        )
        
        with patch('hooptipp.nba.management.commands.backfill_eventoutcome_metadata.Command.batch_fetch_game_data') as mock_batch_fetch:
            mock_batch_fetch.return_value = {
                '12345': {
                    'game_status': 'Final',
                    'home_score': 110,
                    'away_score': 105,
                    'is_live': False
                }
            }
            
            call_command('backfill_eventoutcome_metadata', '--limit', '1')
            
            # Verify only one EventOutcome was updated
            updated_count = EventOutcome.objects.exclude(metadata={}).count()
            self.assertEqual(updated_count, 1)

    def test_error_handling(self):
        """Test that errors are handled gracefully."""
        with patch('hooptipp.nba.management.commands.backfill_eventoutcome_metadata.Command.batch_fetch_game_data') as mock_batch_fetch:
            mock_batch_fetch.side_effect = Exception('API Error')
            
            # Should not raise an exception
            call_command('backfill_eventoutcome_metadata')
            
            # Verify metadata was not updated
            self.event_outcome.refresh_from_db()
            self.assertEqual(self.event_outcome.metadata, {})
