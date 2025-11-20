"""Tests for DBB event source."""

import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from hooptipp.predictions.models import (
    Option,
    OptionCategory,
    PredictionEvent,
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
    def test_sync_events_filters_past_matches(self, mock_build_client):
        """Test that past matches are not synced."""
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

        # Should not create events for past matches
        self.assertEqual(result.events_created, 0)

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

