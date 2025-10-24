"""Tests for the download_team_logos management command."""

import json
import tempfile
from pathlib import Path
from unittest import mock
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.conf import settings

from hooptipp.predictions.models import Option, OptionCategory
from hooptipp.nba.managers import NbaTeamManager


class DownloadTeamLogosCommandTests(TestCase):
    """Tests for the download_team_logos management command."""

    def setUp(self):
        """Set up test data."""
        # Create NBA teams category
        self.teams_cat = OptionCategory.objects.create(
            slug="nba-teams",
            name="NBA Teams",
        )
        
        # Create test NBA teams
        self.celtics = Option.objects.create(
            category=self.teams_cat,
            slug="boston-celtics",
            name="Boston Celtics",
            short_name="BOS",
            external_id="2",
            metadata={
                "city": "Boston",
                "conference": "East",
                "division": "Atlantic",
                "nba_team_id": 1610612738,
                "balldontlie_team_id": 2,
            },
            is_active=True,
        )
        
        self.lakers = Option.objects.create(
            category=self.teams_cat,
            slug="los-angeles-lakers",
            name="Los Angeles Lakers",
            short_name="LAL",
            external_id="14",
            metadata={
                "city": "Los Angeles",
                "conference": "West",
                "division": "Pacific",
                "nba_team_id": 1610612747,
                "balldontlie_team_id": 14,
            },
            is_active=True,
        )

    @override_settings(STATICFILES_DIRS=[tempfile.mkdtemp()])
    @patch('hooptipp.nba.management.commands.download_team_logos.requests.get')
    def test_download_team_logos_success(self, mock_get):
        """Test successful logo download."""
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.content = b'<svg>test logo</svg>'
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Run command
        out = call_command('download_team_logos', verbosity=0)
        
        # Verify requests were made
        self.assertEqual(mock_get.call_count, 2)  # 2 teams
        
        # Check that files were created
        static_dir = Path(settings.STATICFILES_DIRS[0])
        logos_dir = static_dir / 'nba' / 'logos'
        
        self.assertTrue((logos_dir / 'bos.svg').exists())
        self.assertTrue((logos_dir / 'lal.svg').exists())

    @override_settings(STATICFILES_DIRS=[tempfile.mkdtemp()])
    @patch('hooptipp.nba.management.commands.download_team_logos.requests.get')
    def test_download_team_logos_dry_run(self, mock_get):
        """Test dry run mode doesn't download files."""
        # Run command in dry run mode
        out = call_command('download_team_logos', '--dry-run', verbosity=0)
        
        # Verify no requests were made
        mock_get.assert_not_called()
        
        # Check that no files were created
        static_dir = Path(settings.STATICFILES_DIRS[0])
        logos_dir = static_dir / 'nba' / 'logos'
        
        self.assertFalse(logos_dir.exists())

    @override_settings(STATICFILES_DIRS=[tempfile.mkdtemp()])
    @patch('hooptipp.nba.management.commands.download_team_logos.requests.get')
    def test_download_specific_team(self, mock_get):
        """Test downloading logo for a specific team."""
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.content = b'<svg>test logo</svg>'
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Run command for specific team
        out = call_command('download_team_logos', '--team', 'BOS', verbosity=0)
        
        # Verify only one request was made
        self.assertEqual(mock_get.call_count, 1)
        
        # Check that only one file was created
        static_dir = Path(settings.STATICFILES_DIRS[0])
        logos_dir = static_dir / 'nba' / 'logos'
        
        self.assertTrue((logos_dir / 'bos.svg').exists())
        self.assertFalse((logos_dir / 'lal.svg').exists())

    @override_settings(STATICFILES_DIRS=[tempfile.mkdtemp()])
    @patch('hooptipp.nba.management.commands.download_team_logos.requests.get')
    def test_download_png_format(self, mock_get):
        """Test downloading logos in PNG format."""
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.content = b'PNG image data'
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Run command with PNG format
        out = call_command('download_team_logos', '--format', 'png', verbosity=0)
        
        # Verify requests were made with PNG URLs
        self.assertEqual(mock_get.call_count, 2)
        
        # Check PNG URLs were used
        call_args = [call[0][0] for call in mock_get.call_args_list]
        self.assertTrue(any('logo.png' in url for url in call_args))
        
        # Check that PNG files were created
        static_dir = Path(settings.STATICFILES_DIRS[0])
        logos_dir = static_dir / 'nba' / 'logos'
        
        self.assertTrue((logos_dir / 'bos.png').exists())
        self.assertTrue((logos_dir / 'lal.png').exists())

    @override_settings(STATICFILES_DIRS=[tempfile.mkdtemp()])
    @patch('hooptipp.nba.management.commands.download_team_logos.requests.get')
    def test_download_force_overwrite(self, mock_get):
        """Test force download overwrites existing files."""
        # Create existing file
        static_dir = Path(settings.STATICFILES_DIRS[0])
        logos_dir = static_dir / 'nba' / 'logos'
        logos_dir.mkdir(parents=True, exist_ok=True)
        
        existing_file = logos_dir / 'bos.svg'
        existing_file.write_text('old content')
        
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.content = b'<svg>new logo</svg>'
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Run command with force
        out = call_command('download_team_logos', '--force', verbosity=0)
        
        # Verify requests were made
        self.assertEqual(mock_get.call_count, 2)
        
        # Check that file was overwritten
        self.assertTrue(existing_file.exists())
        self.assertEqual(existing_file.read_text(), '<svg>new logo</svg>')

    @override_settings(STATICFILES_DIRS=[tempfile.mkdtemp()])
    @patch('hooptipp.nba.management.commands.download_team_logos.requests.get')
    def test_download_skip_existing(self, mock_get):
        """Test that existing files are skipped without force."""
        # Create existing file
        static_dir = Path(settings.STATICFILES_DIRS[0])
        logos_dir = static_dir / 'nba' / 'logos'
        logos_dir.mkdir(parents=True, exist_ok=True)
        
        existing_file = logos_dir / 'bos.svg'
        existing_file.write_text('existing content')
        
        # Run command without force
        out = call_command('download_team_logos', verbosity=0)
        
        # Verify no requests were made for existing file
        # (should only download LAL since BOS already exists)
        self.assertEqual(mock_get.call_count, 1)
        
        # Check that existing file wasn't changed
        self.assertEqual(existing_file.read_text(), 'existing content')

    @override_settings(STATICFILES_DIRS=[tempfile.mkdtemp()])
    @patch('hooptipp.nba.management.commands.download_team_logos.requests.get')
    def test_download_http_error(self, mock_get):
        """Test handling of HTTP errors."""
        # Mock HTTP error
        mock_get.side_effect = Exception('HTTP 404 Not Found')
        
        # Run command
        out = call_command('download_team_logos', verbosity=0)
        
        # Verify requests were attempted
        self.assertEqual(mock_get.call_count, 2)
        
        # Check that logos directory was created but no files were saved
        static_dir = Path(settings.STATICFILES_DIRS[0])
        logos_dir = static_dir / 'nba' / 'logos'
        
        # Directory should exist but should be empty
        self.assertTrue(logos_dir.exists())
        self.assertEqual(len(list(logos_dir.glob('*.svg'))), 0)

    def test_download_nonexistent_team(self):
        """Test downloading logo for non-existent team."""
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('download_team_logos', '--team', 'INVALID', verbosity=0)

    @override_settings(STATICFILES_DIRS=[tempfile.mkdtemp()])
    def test_team_without_nba_team_id(self):
        """Test team without NBA team ID in metadata."""
        # Create team without NBA team ID
        team_without_id = Option.objects.create(
            category=self.teams_cat,
            slug="test-team",
            name="Test Team",
            short_name="TEST",
            external_id="999",
            metadata={
                "city": "Test City",
                "conference": "Test",
                "division": "Test",
                # No nba_team_id
            },
            is_active=True,
        )
        
        # Run command
        out = call_command('download_team_logos', '--team', 'TEST', verbosity=0)
        
        # Should skip the team without NBA team ID
        # Directory should be created but no files should be saved
        static_dir = Path(settings.STATICFILES_DIRS[0])
        logos_dir = static_dir / 'nba' / 'logos'
        
        # Directory should exist but should be empty
        self.assertTrue(logos_dir.exists())
        self.assertEqual(len(list(logos_dir.glob('*.svg'))), 0)
