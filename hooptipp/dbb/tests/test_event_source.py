"""Tests for DBB event source."""

import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from hooptipp.predictions.models import (
    EventOutcome,
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
)
from hooptipp.dbb.event_source import DbbEventSource
from hooptipp.dbb.models import TrackedLeague, TrackedTeam


class DbbEventSourceTest(TestCase):
    """Tests for DbbEventSource."""

    def setUp(self):
        """Set up test data."""
        self.event_source = DbbEventSource()
        
        # Create test league and teams
        self.league = TrackedLeague.objects.create(
            verband_name='Test Verband',
            verband_id='v1',
            league_name='Test League',
            league_id='l1',
            club_search_term='Test Club',
            is_active=True
        )
        
        self.team1 = TrackedTeam.objects.create(
            tracked_league=self.league,
            team_name='BG Test Team 1',
            team_id='t1',
            is_active=True
        )
        
        self.team2 = TrackedTeam.objects.create(
            tracked_league=self.league,
            team_name='BG Test Team 2',
            team_id='t2',
            is_active=True
        )

    def test_source_properties(self):
        """Test event source properties."""
        self.assertEqual(self.event_source.source_id, 'dbb-slapi')
        self.assertEqual(self.event_source.source_name, 'German Basketball (SLAPI)')
        self.assertIn('dbb-teams', self.event_source.category_slugs)

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_is_configured(self, mock_build_client):
        """Test configuration check."""
        mock_build_client.return_value = MagicMock()
        self.assertTrue(self.event_source.is_configured())

        mock_build_client.return_value = None
        self.assertFalse(self.event_source.is_configured())

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_options(self, mock_build_client):
        """Test syncing team options."""
        mock_build_client.return_value = MagicMock()

        result = self.event_source.sync_options()

        # Should create options for tracked teams
        self.assertGreater(result.options_created, 0)
        
        # Check that category was created
        self.assertTrue(OptionCategory.objects.filter(slug='dbb-teams').exists())
        
        # Check that options were created
        category = OptionCategory.objects.get(slug='dbb-teams')
        self.assertTrue(Option.objects.filter(category=category, name='BG Test Team 1').exists())
        self.assertTrue(Option.objects.filter(category=category, name='BG Test Team 2').exists())

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events(self, mock_build_client):
        """Test syncing match events."""
        # First sync options to create team options
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Sync options first
        self.event_source.sync_options()

        # Mock match data
        future_date = (timezone.now() + timedelta(days=7)).isoformat()
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': future_date,
                'location': 'Test Arena'
            }
        ]

        result = self.event_source.sync_events()

        # Should create prediction events
        self.assertGreater(result.events_created, 0)
        
        # Check that prediction event was created
        self.assertTrue(PredictionEvent.objects.filter(source_id='dbb-slapi').exists())
        
        event = PredictionEvent.objects.get(source_id='dbb-slapi')
        self.assertIn('BG Test Team 1', event.name)
        self.assertIn('BG Test Team 2', event.name)

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events_processes_past_matches(self, mock_build_client):
        """Test that past matches are now synced (to create events and outcomes)."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Sync options first
        self.event_source.sync_options()

        # Mock past match data
        past_date = (timezone.now() - timedelta(days=7)).isoformat()
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': past_date,
                'location': 'Test Arena'
            }
        ]

        result = self.event_source.sync_events()

        # Should create events for past matches now
        self.assertEqual(result.events_created, 1)
        self.assertTrue(PredictionEvent.objects.filter(source_id='dbb-slapi', source_event_id='1').exists())

    def test_parse_datetime(self):
        """Test datetime parsing."""
        # Test ISO format
        dt_str = '2024-03-15T18:30:00+00:00'
        dt = self.event_source._parse_datetime(dt_str)
        self.assertIsNotNone(dt)

        # Test with Z suffix
        dt_str = '2024-03-15T18:30:00Z'
        dt = self.event_source._parse_datetime(dt_str)
        self.assertIsNotNone(dt)

    def test_slugify_team_name(self):
        """Test team name slugification."""
        slug = self.event_source._slugify_team_name('BG Test Team 1')
        self.assertEqual(slug, 'bg-test-team-1')

    def test_extract_short_name(self):
        """Test extracting short name from team name."""
        short_name = self.event_source._extract_short_name('BG Test Team')
        self.assertIsNotNone(short_name)
        self.assertLessEqual(len(short_name), 20)

    def test_parse_score_string(self):
        """Test parsing score strings in various formats."""
        # Test colon format (home:away - European order)
        home, away = self.event_source._parse_score_string('75:90')
        self.assertEqual(home, 75)
        self.assertEqual(away, 90)
        
        # Test dash format
        home, away = self.event_source._parse_score_string('85 - 78')
        self.assertEqual(home, 85)
        self.assertEqual(away, 78)
        
        # Test hyphen format
        home, away = self.event_source._parse_score_string('80-82')
        self.assertEqual(home, 80)
        self.assertEqual(away, 82)
        
        # Test empty string
        home, away = self.event_source._parse_score_string('')
        self.assertIsNone(home)
        self.assertIsNone(away)
        
        # Test invalid format
        home, away = self.event_source._parse_score_string('invalid')
        self.assertIsNone(home)
        self.assertIsNone(away)

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_options_with_logos(self, mock_build_client):
        """Test that team logos are synced to Option metadata."""
        mock_build_client.return_value = MagicMock()
        
        # Add logos to tracked teams
        self.team1.logo = 'team1.svg'
        self.team1.save()
        
        self.team2.logo = 'team2.svg'
        self.team2.save()
        
        result = self.event_source.sync_options()
        
        # Should create options with logo in metadata
        self.assertGreater(result.options_created, 0)
        
        category = OptionCategory.objects.get(slug='dbb-teams')
        team1_option = Option.objects.get(category=category, name='BG Test Team 1')
        team2_option = Option.objects.get(category=category, name='BG Test Team 2')
        
        # Check that logos are in metadata
        self.assertEqual(team1_option.metadata.get('logo'), 'team1.svg')
        self.assertEqual(team2_option.metadata.get('logo'), 'team2.svg')

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_options_without_logos(self, mock_build_client):
        """Test that options work correctly when teams have no logos."""
        mock_build_client.return_value = MagicMock()
        
        result = self.event_source.sync_options()
        
        # Should create options without logo in metadata
        self.assertGreater(result.options_created, 0)
        
        category = OptionCategory.objects.get(slug='dbb-teams')
        team1_option = Option.objects.get(category=category, name='BG Test Team 1')
        
        # Logo should not be in metadata if not set
        self.assertNotIn('logo', team1_option.metadata)

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_options_auto_discovery(self, mock_build_client):
        """Test that logos are auto-discovered for teams without manual logo assignment."""
        mock_build_client.return_value = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test static/dbb directory with logos
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            (static_dbb / 'test-team.svg').touch()
            
            with override_settings(BASE_DIR=tmpdir):
                result = self.event_source.sync_options()
                
                # Should create options
                self.assertGreater(result.options_created, 0)
                
                category = OptionCategory.objects.get(slug='dbb-teams')
                
                # Team 1 should have auto-discovered logo (contains "test-team")
                team1_option = Option.objects.get(category=category, name='BG Test Team 1')
                self.assertEqual(team1_option.metadata.get('logo'), 'test-team.svg')

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_options_manual_overrides_auto_discovery(self, mock_build_client):
        """Test that manually assigned logos take precedence over auto-discovery."""
        mock_build_client.return_value = MagicMock()
        
        # Set manual logo
        self.team1.logo = 'manual-logo.svg'
        self.team1.save()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test static/dbb directory with a matching logo
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            (static_dbb / 'test-team.svg').touch()
            
            with override_settings(BASE_DIR=tmpdir):
                result = self.event_source.sync_options()
                
                category = OptionCategory.objects.get(slug='dbb-teams')
                team1_option = Option.objects.get(category=category, name='BG Test Team 1')
                
                # Should use manual logo, not auto-discovered one
                self.assertEqual(team1_option.metadata.get('logo'), 'manual-logo.svg')

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events_opponent_team_logo_discovery(self, mock_build_client):
        """Test that opponent teams (not tracked) also get logos via auto-discovery."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test static/dbb directory with logos
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            (static_dbb / 'opponent.svg').touch()
            
            with override_settings(BASE_DIR=tmpdir):
                # Sync options first
                self.event_source.sync_options()
                
                # Mock match data with an opponent team not in our tracked teams
                future_date = (timezone.now() + timedelta(days=7)).isoformat()
                mock_client.get_league_matches.return_value = [
                    {
                        'match_id': 1,
                        'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                        'away_team': {'id': 'opp1', 'name': 'Opponent Team FC'},
                        'datetime': future_date,
                        'location': 'Test Arena'
                    }
                ]
                
                result = self.event_source.sync_events()
                
                # Should create event
                self.assertGreater(result.events_created, 0)
                
                # Check that opponent team option was created with logo
                category = OptionCategory.objects.get(slug='dbb-teams')
                opponent_option = Option.objects.get(category=category, name='Opponent Team FC')
                
                # Should have auto-discovered logo
                self.assertEqual(opponent_option.metadata.get('logo'), 'opponent.svg')

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events_filters_cancelled_matches(self, mock_build_client):
        """Test that cancelled matches are not synced."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Sync options first
        self.event_source.sync_options()

        # Mock cancelled match data
        future_date = (timezone.now() + timedelta(days=7)).isoformat()
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': future_date,
                'location': 'Test Arena',
                'is_cancelled': True
            }
        ]

        result = self.event_source.sync_events()

        # Should not create events for cancelled matches
        self.assertEqual(result.events_created, 0)
        self.assertFalse(PredictionEvent.objects.filter(source_id='dbb-slapi').exists())

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events_deactivates_cancelled_matches(self, mock_build_client):
        """Test that existing events are deactivated when match becomes cancelled."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Sync options first
        self.event_source.sync_options()

        # First sync: create an active match
        future_date = (timezone.now() + timedelta(days=7)).isoformat()
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': future_date,
                'location': 'Test Arena',
                'is_cancelled': False
            }
        ]

        result = self.event_source.sync_events()
        self.assertEqual(result.events_created, 1)
        
        event = PredictionEvent.objects.get(source_id='dbb-slapi', source_event_id='1')
        self.assertTrue(event.is_active)

        # Second sync: same match is now cancelled
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': future_date,
                'location': 'Test Arena',
                'is_cancelled': True
            }
        ]

        result = self.event_source.sync_events()
        
        # Event should now be deactivated
        event.refresh_from_db()
        self.assertFalse(event.is_active)

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events_creates_outcome_for_past_match_with_result(self, mock_build_client):
        """Test that outcomes are created for past matches with results."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Sync options first
        self.event_source.sync_options()

        # Mock past match data with score string and is_finished flag
        past_date = (timezone.now() - timedelta(days=7)).isoformat()
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': past_date,
                'location': 'Test Arena',
                'score': '85:78',  # home:away format (home=85, away=78)
                'score_home': 85,  # explicit home score
                'score_away': 78,  # explicit away score
                'is_finished': True,
                'is_cancelled': False
            }
        ]

        result = self.event_source.sync_events()

        # Should create event
        self.assertEqual(result.events_created, 1)
        event = PredictionEvent.objects.get(source_id='dbb-slapi', source_event_id='1')
        
        # Should create outcome
        self.assertTrue(EventOutcome.objects.filter(prediction_event=event).exists())
        outcome = EventOutcome.objects.get(prediction_event=event)
        
        # Check outcome details
        self.assertIsNotNone(outcome.winning_option)
        self.assertEqual(outcome.metadata['home_score'], 85)
        self.assertEqual(outcome.metadata['away_score'], 78)
        
        # Winning team should be home team (85 > 78)
        winning_option = outcome.winning_option
        self.assertEqual(winning_option.option.name, 'BG Test Team 1')

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events_parses_score_string_from_match_data(self, mock_build_client):
        """Test that score strings are parsed correctly from match data."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Sync options first
        self.event_source.sync_options()

        # Mock past match data with score string (format: home:away - European order)
        past_date = (timezone.now() - timedelta(days=7)).isoformat()
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': past_date,
                'location': 'Test Arena',
                'score': '75:90',  # home:away format (home=75, away=90)
                'score_home': 75,  # explicit home score
                'score_away': 90,  # explicit away score
                'is_finished': True,
                'is_cancelled': False
            }
        ]

        result = self.event_source.sync_events()

        # Should create event
        self.assertEqual(result.events_created, 1)
        event = PredictionEvent.objects.get(source_id='dbb-slapi', source_event_id='1')
        
        # Should create outcome with parsed scores
        self.assertTrue(EventOutcome.objects.filter(prediction_event=event).exists())
        outcome = EventOutcome.objects.get(prediction_event=event)
        self.assertEqual(outcome.metadata['home_score'], 75)  # Home team score
        self.assertEqual(outcome.metadata['away_score'], 90)  # Away team score
        self.assertEqual(outcome.metadata['score_string'], '75:90')

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events_uses_explicit_score_fields(self, mock_build_client):
        """Test that explicit score_home and score_away fields are used when available."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Sync options first
        self.event_source.sync_options()

        # Mock past match data with explicit score fields (no score string)
        past_date = (timezone.now() - timedelta(days=7)).isoformat()
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': past_date,
                'location': 'Test Arena',
                'score_home': 87,  # explicit home score
                'score_away': 51,  # explicit away score
                'is_finished': True,
                'is_cancelled': False
            }
        ]

        result = self.event_source.sync_events()

        # Should create event
        self.assertEqual(result.events_created, 1)
        event = PredictionEvent.objects.get(source_id='dbb-slapi', source_event_id='1')
        
        # Should create outcome with explicit scores
        self.assertTrue(EventOutcome.objects.filter(prediction_event=event).exists())
        outcome = EventOutcome.objects.get(prediction_event=event)
        self.assertEqual(outcome.metadata['home_score'], 87)  # Home team score from explicit field
        self.assertEqual(outcome.metadata['away_score'], 51)  # Away team score from explicit field
        # Score string should be generated from explicit fields
        self.assertEqual(outcome.metadata['score_string'], '87:51')

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events_fallback_to_score_string(self, mock_build_client):
        """Test that score string parsing is used as fallback when explicit fields are missing."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Sync options first
        self.event_source.sync_options()

        # Mock past match data with only score string (no explicit fields)
        past_date = (timezone.now() - timedelta(days=7)).isoformat()
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': past_date,
                'location': 'Test Arena',
                'score': '92:68',  # only score string, no explicit fields
                'is_finished': True,
                'is_cancelled': False
            }
        ]

        result = self.event_source.sync_events()

        # Should create event
        self.assertEqual(result.events_created, 1)
        event = PredictionEvent.objects.get(source_id='dbb-slapi', source_event_id='1')
        
        # Should create outcome with parsed scores from string
        self.assertTrue(EventOutcome.objects.filter(prediction_event=event).exists())
        outcome = EventOutcome.objects.get(prediction_event=event)
        self.assertEqual(outcome.metadata['home_score'], 92)  # Parsed from string
        self.assertEqual(outcome.metadata['away_score'], 68)  # Parsed from string
        self.assertEqual(outcome.metadata['score_string'], '92:68')

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events_skips_outcome_for_past_match_without_result(self, mock_build_client):
        """Test that outcomes are not created for past matches without final results."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Sync options first
        self.event_source.sync_options()

        # Mock past match data without score or is_finished flag
        past_date = (timezone.now() - timedelta(days=7)).isoformat()
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': past_date,
                'location': 'Test Arena',
                'is_finished': False,
                'is_cancelled': False
            }
        ]

        result = self.event_source.sync_events()

        # Should create event
        self.assertEqual(result.events_created, 1)
        event = PredictionEvent.objects.get(source_id='dbb-slapi', source_event_id='1')
        
        # Should NOT create outcome (match not finished and no score)
        self.assertFalse(EventOutcome.objects.filter(prediction_event=event).exists())

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events_skips_outcome_for_tie(self, mock_build_client):
        """Test that outcomes are not created for matches that end in a tie."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Sync options first
        self.event_source.sync_options()

        # Mock past match data with tie score
        past_date = (timezone.now() - timedelta(days=7)).isoformat()
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': past_date,
                'location': 'Test Arena',
                'score': '80:80',  # tie
                'score_home': 80,  # explicit home score
                'score_away': 80,  # explicit away score
                'is_finished': True,
                'is_cancelled': False
            }
        ]

        result = self.event_source.sync_events()

        # Should create event
        self.assertEqual(result.events_created, 1)
        event = PredictionEvent.objects.get(source_id='dbb-slapi', source_event_id='1')
        
        # Should NOT create outcome (tie)
        self.assertFalse(EventOutcome.objects.filter(prediction_event=event).exists())

    @patch('hooptipp.dbb.event_source.build_slapi_client')
    def test_sync_events_does_not_duplicate_outcome(self, mock_build_client):
        """Test that outcomes are not created if one already exists."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Sync options first
        self.event_source.sync_options()

        # Mock past match data with score string
        past_date = (timezone.now() - timedelta(days=7)).isoformat()
        mock_client.get_league_matches.return_value = [
            {
                'match_id': 1,
                'home_team': {'id': 't1', 'name': 'BG Test Team 1'},
                'away_team': {'id': 't2', 'name': 'BG Test Team 2'},
                'datetime': past_date,
                'location': 'Test Arena',
                'score': '85:78',  # home:away format (home=85, away=78)
                'score_home': 85,  # explicit home score
                'score_away': 78,  # explicit away score
                'is_finished': True,
                'is_cancelled': False
            }
        ]

        # First sync - creates event and outcome
        result1 = self.event_source.sync_events()
        self.assertEqual(result1.events_created, 1)
        event = PredictionEvent.objects.get(source_id='dbb-slapi', source_event_id='1')
        self.assertTrue(EventOutcome.objects.filter(prediction_event=event).exists())
        
        # Count outcomes before second sync
        outcome_count_before = EventOutcome.objects.filter(prediction_event=event).count()
        
        # Second sync - should not create duplicate outcome
        result2 = self.event_source.sync_events()
        self.assertEqual(result2.events_updated, 1)  # Event updated, not created
        
        # Should still have only one outcome
        outcome_count_after = EventOutcome.objects.filter(prediction_event=event).count()
        self.assertEqual(outcome_count_before, outcome_count_after)

