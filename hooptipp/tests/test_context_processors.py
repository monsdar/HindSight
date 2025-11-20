"""Tests for context processors."""

from django.conf import settings
from django.test import TestCase, RequestFactory, override_settings

from hooptipp.context_processors import page_customization


class PageCustomizationContextProcessorTestCase(TestCase):
    """Tests for the page_customization context processor."""

    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get('/')

    def test_default_values(self):
        """Test that default PAGE_TITLE and PAGE_SLOGAN are returned."""
        context = page_customization(self.request)
        
        self.assertIn('PAGE_TITLE', context)
        self.assertIn('PAGE_SLOGAN', context)
        self.assertEqual(context['PAGE_TITLE'], settings.PAGE_TITLE)
        self.assertEqual(context['PAGE_SLOGAN'], settings.PAGE_SLOGAN)

    @override_settings(PAGE_TITLE='Custom Title')
    def test_custom_title(self):
        """Test that custom PAGE_TITLE is returned."""
        context = page_customization(self.request)
        
        self.assertEqual(context['PAGE_TITLE'], 'Custom Title')

    @override_settings(PAGE_SLOGAN='Custom Slogan')
    def test_custom_slogan(self):
        """Test that custom PAGE_SLOGAN is returned."""
        context = page_customization(self.request)
        
        self.assertEqual(context['PAGE_SLOGAN'], 'Custom Slogan')

    @override_settings(PAGE_TITLE='NBA Predictions', PAGE_SLOGAN='Who will win?')
    def test_both_custom_values(self):
        """Test that both custom values are returned."""
        context = page_customization(self.request)
        
        self.assertEqual(context['PAGE_TITLE'], 'NBA Predictions')
        self.assertEqual(context['PAGE_SLOGAN'], 'Who will win?')

    def test_theme_palette_included(self):
        """Test that active_theme_palette is included in context."""
        context = page_customization(self.request)
        
        self.assertIn('active_theme_palette', context)
        self.assertIn('primary', context['active_theme_palette'])
        self.assertIn('secondary', context['active_theme_palette'])
        
        # Verify colors are hex codes
        primary = context['active_theme_palette']['primary']
        secondary = context['active_theme_palette']['secondary']
        self.assertTrue(primary.startswith('#'))
        self.assertTrue(secondary.startswith('#'))

