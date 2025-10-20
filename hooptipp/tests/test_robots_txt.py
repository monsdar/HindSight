"""Tests for robots.txt endpoint."""

from django.test import TestCase
from django.urls import reverse


class RobotsTxtTestCase(TestCase):
    """Test cases for robots.txt endpoint."""

    def test_robots_txt_endpoint_exists(self):
        """Test that robots.txt endpoint is accessible."""
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)

    def test_robots_txt_content_type(self):
        """Test that robots.txt returns correct content type."""
        response = self.client.get('/robots.txt')
        self.assertEqual(response['Content-Type'], 'text/plain')

    def test_robots_txt_content(self):
        """Test that robots.txt contains expected content."""
        response = self.client.get('/robots.txt')
        content = response.content.decode('utf-8')
        
        # Check that it contains the standard robots.txt directives
        self.assertIn('User-agent: *', content)
        self.assertIn('Disallow: /', content)
        
        # Check that it contains our privacy notice
        self.assertIn('This site is private', content)
        self.assertIn('should not be indexed or scraped', content)
        self.assertIn('No AI training data collection allowed', content)

    def test_robots_txt_url_name(self):
        """Test that robots.txt can be accessed via URL name."""
        response = self.client.get(reverse('robots_txt'))
        self.assertEqual(response.status_code, 200)
