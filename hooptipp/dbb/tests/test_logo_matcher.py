"""Tests for DBB logo matcher utility."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings

from hooptipp.dbb.logo_matcher import (
    discover_logo_files,
    find_logo_for_team,
    get_logo_for_team,
    normalize_text,
)


class NormalizeTextTestCase(TestCase):
    """Test text normalization."""

    def test_lowercase_conversion(self):
        """Test that text is converted to lowercase."""
        self.assertEqual(normalize_text("HELLO WORLD"), "hello world")
        self.assertEqual(normalize_text("Mixed Case"), "mixed case")

    def test_german_umlauts(self):
        """Test German umlaut conversion."""
        self.assertEqual(normalize_text("Müller"), "mueller")
        self.assertEqual(normalize_text("Schäfer"), "schaefer")
        self.assertEqual(normalize_text("König"), "koenig")
        self.assertEqual(normalize_text("Straße"), "strasse")

    def test_special_character_removal(self):
        """Test that special characters are removed."""
        self.assertEqual(normalize_text("hello@world"), "helloworld")
        self.assertEqual(normalize_text("team.name"), "teamname")
        self.assertEqual(normalize_text("BG (Berlin)"), "bg berlin")

    def test_hyphen_conversion(self):
        """Test that hyphens are converted to spaces for better matching."""
        self.assertEqual(normalize_text("bierden-bassen"), "bierden bassen")
        self.assertEqual(normalize_text("TV-Bremen"), "tv bremen")

    def test_multiple_spaces(self):
        """Test that multiple spaces are collapsed."""
        self.assertEqual(normalize_text("hello   world"), "hello world")
        self.assertEqual(normalize_text("  spaces  "), "spaces")

    def test_empty_string(self):
        """Test empty string handling."""
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")


class DiscoverLogoFilesTestCase(TestCase):
    """Test logo file discovery."""

    def test_discover_svg_files(self):
        """Test discovering SVG logo files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test static/dbb directory
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            
            # Create test logo files
            (static_dbb / 'team-one.svg').touch()
            (static_dbb / 'team-two.png').touch()
            (static_dbb / 'README.md').touch()  # Should be ignored
            
            with override_settings(BASE_DIR=tmpdir):
                logo_map = discover_logo_files()
                
                # Hyphens are converted to spaces in normalization
                self.assertIn('team one', logo_map)
                self.assertIn('team two', logo_map)
                self.assertEqual(logo_map['team one'], 'team-one.svg')
                self.assertEqual(logo_map['team two'], 'team-two.png')
                self.assertNotIn('readme', logo_map)

    def test_discover_with_special_characters(self):
        """Test discovering logos with special characters in filenames."""
        with tempfile.TemporaryDirectory() as tmpdir:
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            
            (static_dbb / 'bg-müller.svg').touch()
            
            with override_settings(BASE_DIR=tmpdir):
                logo_map = discover_logo_files()
                
                # Filename is normalized (hyphens to spaces, umlauts converted)
                self.assertIn('bg mueller', logo_map)
                # But original filename is preserved
                self.assertEqual(logo_map['bg mueller'], 'bg-müller.svg')

    def test_discover_no_directory(self):
        """Test handling when static/dbb directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(BASE_DIR=tmpdir):
                logo_map = discover_logo_files()
                
                self.assertEqual(logo_map, {})

    def test_discover_multiple_formats(self):
        """Test discovering logos in different formats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            
            (static_dbb / 'team.svg').touch()
            (static_dbb / 'logo.png').touch()
            (static_dbb / 'badge.jpg').touch()
            (static_dbb / 'icon.jpeg').touch()
            (static_dbb / 'doc.txt').touch()  # Should be ignored
            
            with override_settings(BASE_DIR=tmpdir):
                logo_map = discover_logo_files()
                
                self.assertEqual(len(logo_map), 4)
                self.assertIn('team', logo_map)
                self.assertIn('logo', logo_map)
                self.assertIn('badge', logo_map)
                self.assertIn('icon', logo_map)
                self.assertNotIn('doc', logo_map)


class FindLogoForTeamTestCase(TestCase):
    """Test finding logos for teams."""

    def test_exact_substring_match(self):
        """Test exact substring matching."""
        # Note: slugs use space-normalized format (hyphens converted to spaces)
        logo_map = {
            'bierden bassen': 'bierden-bassen.svg',
            'tv bremen': 'tv-bremen.svg',
        }
        
        result = find_logo_for_team('BG Bierden-Bassen Achim', logo_map)
        self.assertEqual(result, 'bierden-bassen.svg')
        
        result = find_logo_for_team('TV Bremen', logo_map)
        self.assertEqual(result, 'tv-bremen.svg')

    def test_no_match(self):
        """Test when no logo matches."""
        logo_map = {
            'team-one': 'team-one.svg',
        }
        
        result = find_logo_for_team('Unknown Team', logo_map)
        self.assertEqual(result, '')

    def test_longest_match_preferred(self):
        """Test that longest matching slug is preferred."""
        logo_map = {
            'bremen': 'bremen.svg',
            'tv bremen': 'tv-bremen.svg',
        }
        
        # "tv bremen" is longer and more specific
        result = find_logo_for_team('TV Bremen Basketball', logo_map)
        self.assertEqual(result, 'tv-bremen.svg')

    def test_case_insensitive_matching(self):
        """Test that matching is case insensitive."""
        logo_map = {
            'werder': 'werder.svg',
        }
        
        result = find_logo_for_team('SG Werder Bremen', logo_map)
        self.assertEqual(result, 'werder.svg')
        
        result = find_logo_for_team('SG WERDER BREMEN', logo_map)
        self.assertEqual(result, 'werder.svg')

    def test_umlaut_matching(self):
        """Test matching with German umlauts."""
        logo_map = {
            'mueller': 'mueller.svg',
        }
        
        # Team name with umlaut should match normalized filename
        result = find_logo_for_team('SV Müller', logo_map)
        self.assertEqual(result, 'mueller.svg')

    def test_special_character_handling(self):
        """Test matching with special characters."""
        logo_map = {
            'bg achim': 'bg-achim.svg',
        }
        
        result = find_logo_for_team('BG (Achim)', logo_map)
        self.assertEqual(result, 'bg-achim.svg')

    def test_empty_team_name(self):
        """Test handling of empty team name."""
        logo_map = {'team': 'team.svg'}
        
        result = find_logo_for_team('', logo_map)
        self.assertEqual(result, '')
        
        result = find_logo_for_team(None, logo_map)
        self.assertEqual(result, '')

    def test_empty_logo_map(self):
        """Test handling of empty logo map."""
        result = find_logo_for_team('Any Team', {})
        self.assertEqual(result, '')

    def test_auto_discovery_when_no_map_provided(self):
        """Test that logos are auto-discovered when no map provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            (static_dbb / 'test-team.svg').touch()
            
            with override_settings(BASE_DIR=tmpdir):
                result = find_logo_for_team('Test Team FC')
                self.assertEqual(result, 'test-team.svg')


class GetLogoForTeamTestCase(TestCase):
    """Test getting logo with manual override support."""

    def test_manual_logo_preferred(self):
        """Test that manually assigned logo takes precedence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            (static_dbb / 'auto-discovered.svg').touch()
            
            with override_settings(BASE_DIR=tmpdir):
                # Even though auto-discovered.svg would match, manual assignment wins
                result = get_logo_for_team('Auto Discovered Team', 'manual-logo.svg')
                self.assertEqual(result, 'manual-logo.svg')

    def test_auto_discovery_fallback(self):
        """Test that auto-discovery is used when no manual logo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            (static_dbb / 'team-logo.svg').touch()
            
            with override_settings(BASE_DIR=tmpdir):
                result = get_logo_for_team('Team Logo FC', '')
                self.assertEqual(result, 'team-logo.svg')

    def test_empty_manual_logo(self):
        """Test that empty string manual logo triggers auto-discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            (static_dbb / 'auto.svg').touch()
            
            with override_settings(BASE_DIR=tmpdir):
                result = get_logo_for_team('Auto Team', '')
                self.assertEqual(result, 'auto.svg')

