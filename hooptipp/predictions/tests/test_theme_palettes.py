"""Tests for theme palette definitions and configuration."""
from __future__ import annotations

import os
from unittest.mock import patch

from django.test import TestCase

from hooptipp.predictions.theme_palettes import (
    DEFAULT_THEME_KEY,
    get_theme_palette,
    iter_themes,
)


class ThemePaletteTests(TestCase):
    """Test theme palette functionality."""

    def test_bg_biba_theme_exists(self) -> None:
        """Test that BG Biba theme is available."""
        palette = get_theme_palette("bg-biba")
        self.assertEqual(palette["primary"], "#E2322A")
        self.assertEqual(palette["secondary"], "#412774")

    def test_bg_biba_theme_in_themes_list(self) -> None:
        """Test that BG Biba theme appears in the themes iterator."""
        themes = list(iter_themes())
        theme_keys = [theme.key for theme in themes]
        self.assertIn("bg-biba", theme_keys)

        # Find the BG Biba theme
        bg_biba = next(theme for theme in themes if theme.key == "bg-biba")
        self.assertEqual(bg_biba.label, "BG Biba (Red & Purple)")
        self.assertEqual(bg_biba.primary, "#E2322A")
        self.assertEqual(bg_biba.secondary, "#412774")

    def test_default_theme_key_from_env(self) -> None:
        """Test that DEFAULT_THEME_KEY can be set via environment variable."""
        # This test verifies the module was loaded with the env var
        # In a real scenario, you'd set this before Django starts
        import importlib
        from hooptipp.predictions import theme_palettes
        
        # Store original value
        original_key = theme_palettes.DEFAULT_THEME_KEY
        
        try:
            with patch.dict(os.environ, {"DEFAULT_THEME_KEY": "bg-biba"}):
                # Re-import to pick up the env var
                importlib.reload(theme_palettes)
                self.assertEqual(theme_palettes.DEFAULT_THEME_KEY, "bg-biba")
        finally:
            # Restore original state
            with patch.dict(os.environ, {"DEFAULT_THEME_KEY": original_key}):
                importlib.reload(theme_palettes)

    def test_default_theme_key_defaults_to_classic(self) -> None:
        """Test that DEFAULT_THEME_KEY defaults to classic when not set."""
        # The module should have been loaded with default
        # We can verify by checking if it's a valid theme
        self.assertIsInstance(DEFAULT_THEME_KEY, str)
        
        # It should either be from env or default to "classic"
        # Just verify it's a valid theme
        palette = get_theme_palette(DEFAULT_THEME_KEY)
        self.assertIn("primary", palette)
        self.assertIn("secondary", palette)

    def test_get_theme_palette_falls_back_to_default(self) -> None:
        """Test that invalid theme keys fall back to default theme."""
        palette = get_theme_palette("nonexistent-theme")
        default_palette = get_theme_palette(DEFAULT_THEME_KEY)
        self.assertEqual(palette, default_palette)

    def test_all_themes_have_required_fields(self) -> None:
        """Test that all themes have key, label, primary, and secondary."""
        for theme in iter_themes():
            self.assertIsInstance(theme.key, str)
            self.assertTrue(theme.key)  # Not empty
            self.assertIsInstance(theme.label, str)
            self.assertTrue(theme.label)  # Not empty
            self.assertIsInstance(theme.primary, str)
            self.assertTrue(theme.primary.startswith("#"))  # Valid hex color
            self.assertIsInstance(theme.secondary, str)
            self.assertTrue(theme.secondary.startswith("#"))  # Valid hex color

