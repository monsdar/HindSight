"""Tests for Impressum and Datenschutz features."""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from hooptipp.predictions.models import DatenschutzSection, ImpressumSection


class ImpressumSectionModelTests(TestCase):
    """Tests for ImpressumSection model."""

    def test_create_impressum_section(self):
        """Test creating an ImpressumSection."""
        section = ImpressumSection.objects.create(
            caption='Contact Information',
            text='**Email:** contact@example.com',
            order_number=1
        )
        
        self.assertEqual(section.caption, 'Contact Information')
        self.assertEqual(section.text, '**Email:** contact@example.com')
        self.assertEqual(section.order_number, 1)
        self.assertIsNotNone(section.created_at)
        self.assertIsNotNone(section.updated_at)

    def test_impressum_section_str(self):
        """Test ImpressumSection string representation."""
        section = ImpressumSection.objects.create(
            caption='Legal Notice',
            text='Some legal text',
            order_number=0
        )
        
        self.assertEqual(str(section), 'Legal Notice')

    def test_impressum_section_ordering(self):
        """Test that sections are ordered by order_number then caption."""
        section1 = ImpressumSection.objects.create(
            caption='Section B',
            text='Text B',
            order_number=2
        )
        section2 = ImpressumSection.objects.create(
            caption='Section A',
            text='Text A',
            order_number=1
        )
        section3 = ImpressumSection.objects.create(
            caption='Section C',
            text='Text C',
            order_number=1
        )
        
        sections = list(ImpressumSection.objects.all())
        
        # Should be ordered by order_number first, then caption
        self.assertEqual(sections[0], section2)  # order_number=1, caption='Section A'
        self.assertEqual(sections[1], section3)  # order_number=1, caption='Section C'
        self.assertEqual(sections[2], section1)  # order_number=2, caption='Section B'

    def test_impressum_section_default_order_number(self):
        """Test that order_number defaults to 0."""
        section = ImpressumSection.objects.create(
            caption='Test Section',
            text='Test text'
        )
        
        self.assertEqual(section.order_number, 0)


class ImpressumAPITests(TestCase):
    """Tests for Impressum API endpoint."""

    def setUp(self):
        self.client = Client()

    def test_get_impressum_empty(self):
        """Test getting Impressum when no sections exist."""
        response = self.client.get('/api/impressum/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('sections', data)
        self.assertEqual(len(data['sections']), 0)

    def test_get_impressum_with_sections(self):
        """Test getting Impressum with multiple sections."""
        section1 = ImpressumSection.objects.create(
            caption='Contact',
            text='**Email:** test@example.com',
            order_number=1
        )
        section2 = ImpressumSection.objects.create(
            caption='Legal',
            text='This is a legal notice.',
            order_number=0
        )
        
        response = self.client.get('/api/impressum/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('sections', data)
        self.assertEqual(len(data['sections']), 2)
        
        # Should be ordered by order_number
        self.assertEqual(data['sections'][0]['caption'], 'Legal')
        self.assertEqual(data['sections'][0]['order_number'], 0)
        self.assertEqual(data['sections'][1]['caption'], 'Contact')
        self.assertEqual(data['sections'][1]['order_number'], 1)

    def test_get_impressum_markdown_rendering(self):
        """Test that markdown text is rendered to HTML."""
        section = ImpressumSection.objects.create(
            caption='Test',
            text='**Bold text** and *italic text*',
            order_number=0
        )
        
        response = self.client.get('/api/impressum/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['sections']), 1)
        
        html = data['sections'][0]['text_html']
        # Markdown2 should convert **Bold text** to <strong>Bold text</strong>
        self.assertIn('<strong>Bold text</strong>', html)
        self.assertIn('<em>italic text</em>', html)

    def test_get_impressum_public_access(self):
        """Test that Impressum API is publicly accessible (no authentication required)."""
        section = ImpressumSection.objects.create(
            caption='Public Section',
            text='This is public',
            order_number=0
        )
        
        # Make request without authentication
        response = self.client.get('/api/impressum/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['sections']), 1)
        self.assertEqual(data['sections'][0]['caption'], 'Public Section')

    def test_get_impressum_ordering_with_same_order_number(self):
        """Test ordering when multiple sections have the same order_number."""
        section1 = ImpressumSection.objects.create(
            caption='Section B',
            text='Text B',
            order_number=1
        )
        section2 = ImpressumSection.objects.create(
            caption='Section A',
            text='Text A',
            order_number=1
        )
        
        response = self.client.get('/api/impressum/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['sections']), 2)
        
        # Should be ordered by caption when order_number is the same
        self.assertEqual(data['sections'][0]['caption'], 'Section A')
        self.assertEqual(data['sections'][1]['caption'], 'Section B')

    def test_get_impressum_complex_markdown(self):
        """Test rendering of complex markdown content."""
        section = ImpressumSection.objects.create(
            caption='Complex Content',
            text='''
# Heading

This is a paragraph with **bold** and *italic* text.

- List item 1
- List item 2

[Link text](https://example.com)
            ''',
            order_number=0
        )
        
        response = self.client.get('/api/impressum/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        html = data['sections'][0]['text_html']
        
        # Check that markdown elements are converted
        self.assertIn('<h1>Heading</h1>', html)
        self.assertIn('<strong>bold</strong>', html)
        self.assertIn('<em>italic</em>', html)
        self.assertIn('<li>', html)  # List items
        self.assertIn('<a href="https://example.com">', html)  # Link


class DatenschutzSectionModelTests(TestCase):
    """Tests for DatenschutzSection model."""

    def test_create_datenschutz_section(self):
        """Test creating a DatenschutzSection."""
        section = DatenschutzSection.objects.create(
            caption='Data Collection',
            text='**We collect:** Personal information',
            order_number=1
        )
        
        self.assertEqual(section.caption, 'Data Collection')
        self.assertEqual(section.text, '**We collect:** Personal information')
        self.assertEqual(section.order_number, 1)
        self.assertIsNotNone(section.created_at)
        self.assertIsNotNone(section.updated_at)

    def test_datenschutz_section_str(self):
        """Test DatenschutzSection string representation."""
        section = DatenschutzSection.objects.create(
            caption='Privacy Policy',
            text='Some privacy text',
            order_number=0
        )
        
        self.assertEqual(str(section), 'Privacy Policy')

    def test_datenschutz_section_ordering(self):
        """Test that sections are ordered by order_number then caption."""
        section1 = DatenschutzSection.objects.create(
            caption='Section B',
            text='Text B',
            order_number=2
        )
        section2 = DatenschutzSection.objects.create(
            caption='Section A',
            text='Text A',
            order_number=1
        )
        section3 = DatenschutzSection.objects.create(
            caption='Section C',
            text='Text C',
            order_number=1
        )
        
        sections = list(DatenschutzSection.objects.all())
        
        # Should be ordered by order_number first, then caption
        self.assertEqual(sections[0], section2)  # order_number=1, caption='Section A'
        self.assertEqual(sections[1], section3)  # order_number=1, caption='Section C'
        self.assertEqual(sections[2], section1)  # order_number=2, caption='Section B'


class DatenschutzAPITests(TestCase):
    """Tests for Datenschutz API endpoint."""

    def setUp(self):
        self.client = Client()

    def test_get_datenschutz_empty(self):
        """Test getting Datenschutz when no sections exist."""
        response = self.client.get('/api/datenschutz/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('sections', data)
        self.assertEqual(len(data['sections']), 0)

    def test_get_datenschutz_with_sections(self):
        """Test getting Datenschutz with multiple sections."""
        section1 = DatenschutzSection.objects.create(
            caption='Data Collection',
            text='**We collect:** Personal information',
            order_number=1
        )
        section2 = DatenschutzSection.objects.create(
            caption='Introduction',
            text='This is our privacy policy.',
            order_number=0
        )
        
        response = self.client.get('/api/datenschutz/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('sections', data)
        self.assertEqual(len(data['sections']), 2)
        
        # Should be ordered by order_number
        self.assertEqual(data['sections'][0]['caption'], 'Introduction')
        self.assertEqual(data['sections'][0]['order_number'], 0)
        self.assertEqual(data['sections'][1]['caption'], 'Data Collection')
        self.assertEqual(data['sections'][1]['order_number'], 1)

    def test_get_datenschutz_markdown_rendering(self):
        """Test that markdown text is rendered to HTML."""
        section = DatenschutzSection.objects.create(
            caption='Test',
            text='**Bold text** and *italic text*',
            order_number=0
        )
        
        response = self.client.get('/api/datenschutz/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['sections']), 1)
        
        html = data['sections'][0]['text_html']
        # Markdown2 should convert **Bold text** to <strong>Bold text</strong>
        self.assertIn('<strong>Bold text</strong>', html)
        self.assertIn('<em>italic text</em>', html)

    def test_get_datenschutz_public_access(self):
        """Test that Datenschutz API is publicly accessible (no authentication required)."""
        section = DatenschutzSection.objects.create(
            caption='Public Section',
            text='This is public',
            order_number=0
        )
        
        # Make request without authentication
        response = self.client.get('/api/datenschutz/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['sections']), 1)
        self.assertEqual(data['sections'][0]['caption'], 'Public Section')

