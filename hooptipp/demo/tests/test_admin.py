"""Tests for demo admin functionality."""

import unittest
from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from hooptipp.demo.admin import DemoPseudoModel
from hooptipp.predictions.models import (
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
)


class DemoAdminTestCase(TestCase):
    """Test case for demo admin functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='admin123'
        )
        self.client.login(username='admin', password='admin123')

    def test_create_demo_events_view_get(self):
        """Test GET request to create demo events view."""
        url = reverse('admin:demo_add_demo_events')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Demo Prediction Events')
        self.assertContains(response, 'Yes/No Question')
        self.assertContains(response, 'Color Choice')
        self.assertContains(response, 'Bonus Event')
        self.assertContains(response, 'Player Championship')

    def test_create_demo_events_post(self):
        """Test POST request creates demo events."""
        url = reverse('admin:demo_add_demo_events')
        
        # Verify no demo events exist initially
        self.assertEqual(
            PredictionEvent.objects.filter(source_id='demo').count(),
            0
        )
        
        response = self.client.post(url)
        
        # Should redirect to prediction event list
        self.assertEqual(response.status_code, 302)
        self.assertIn('predictionevent', response.url)
        
        # Verify demo events were created
        demo_events = PredictionEvent.objects.filter(source_id='demo')
        self.assertEqual(demo_events.count(), 4)
        
        # Verify tip type was created
        self.assertTrue(TipType.objects.filter(slug='demo-tips').exists())
        tip_type = TipType.objects.get(slug='demo-tips')
        self.assertEqual(tip_type.name, 'Demo Tips')

    def test_demo_option_categories_created(self):
        """Test that demo option categories are created."""
        url = reverse('admin:demo_add_demo_events')
        self.client.post(url)
        
        # Verify categories exist
        self.assertTrue(OptionCategory.objects.filter(slug='demo-yesno').exists())
        self.assertTrue(OptionCategory.objects.filter(slug='demo-colors').exists())
        self.assertTrue(OptionCategory.objects.filter(slug='demo-characters').exists())

    def test_demo_options_created(self):
        """Test that demo options are created."""
        url = reverse('admin:demo_add_demo_events')
        self.client.post(url)
        
        # Verify yes/no options
        yesno_cat = OptionCategory.objects.get(slug='demo-yesno')
        self.assertEqual(Option.objects.filter(category=yesno_cat).count(), 2)
        
        # Verify color options
        colors_cat = OptionCategory.objects.get(slug='demo-colors')
        self.assertEqual(Option.objects.filter(category=colors_cat).count(), 5)
        
        # Verify character options
        chars_cat = OptionCategory.objects.get(slug='demo-characters')
        self.assertEqual(Option.objects.filter(category=chars_cat).count(), 4)

    def test_demo_events_timing(self):
        """Test that demo events have correct timing."""
        url = reverse('admin:demo_add_demo_events')
        now = timezone.now()
        
        self.client.post(url)
        
        for event in PredictionEvent.objects.filter(source_id='demo'):
            # Opens at should be around now (within 1 second)
            self.assertLessEqual(
                abs((event.opens_at - now).total_seconds()),
                1.0
            )
            
            # Deadline should be ~5 minutes from now
            deadline_diff = (event.deadline - now).total_seconds()
            self.assertGreaterEqual(deadline_diff, 4 * 60)  # At least 4 minutes
            self.assertLessEqual(deadline_diff, 6 * 60)  # At most 6 minutes
            
            # Event should be active
            self.assertTrue(event.is_active)
            self.assertTrue(event.is_visible())

    def test_yesno_event_created(self):
        """Test yes/no event is created correctly."""
        url = reverse('admin:demo_add_demo_events')
        self.client.post(url)
        
        # Find the yes/no event
        events = PredictionEvent.objects.filter(
            source_id='demo',
            metadata__event_type='yesno'
        )
        self.assertEqual(events.count(), 1)
        
        event = events.first()
        self.assertIn('rain', event.name.lower())
        self.assertEqual(event.target_kind, PredictionEvent.TargetKind.GENERIC)
        self.assertEqual(event.selection_mode, PredictionEvent.SelectionMode.CURATED)
        self.assertEqual(event.points, 1)
        self.assertFalse(event.is_bonus_event)
        
        # Verify options
        self.assertEqual(event.options.count(), 2)

    def test_colors_event_created(self):
        """Test colors event is created correctly."""
        url = reverse('admin:demo_add_demo_events')
        self.client.post(url)
        
        # Find the colors event
        events = PredictionEvent.objects.filter(
            source_id='demo',
            metadata__event_type='colors'
        )
        self.assertEqual(events.count(), 1)
        
        event = events.first()
        self.assertIn('color', event.name.lower())
        self.assertEqual(event.points, 2)
        
        # Verify 5 color options
        self.assertEqual(event.options.count(), 5)

    def test_bonus_event_created(self):
        """Test bonus event is created correctly."""
        url = reverse('admin:demo_add_demo_events')
        self.client.post(url)
        
        # Find the bonus event
        events = PredictionEvent.objects.filter(
            source_id='demo',
            metadata__event_type='bonus'
        )
        self.assertEqual(events.count(), 1)
        
        event = events.first()
        self.assertIn('BONUS', event.name)
        self.assertEqual(event.points, 5)
        self.assertTrue(event.is_bonus_event)
        self.assertTrue(event.metadata.get('special'))

    def test_player_event_created(self):
        """Test player event is created correctly."""
        url = reverse('admin:demo_add_demo_events')
        self.client.post(url)
        
        # Find the player event
        events = PredictionEvent.objects.filter(
            source_id='demo',
            metadata__event_type='player'
        )
        self.assertEqual(events.count(), 1)
        
        event = events.first()
        self.assertIn('champion', event.name.lower())
        self.assertEqual(event.target_kind, PredictionEvent.TargetKind.PLAYER)
        self.assertEqual(event.points, 3)
        
        # Verify 4 character options
        self.assertEqual(event.options.count(), 4)

    def test_duplicate_events_not_created(self):
        """Test that multiple calls create events with unique IDs."""
        url = reverse('admin:demo_add_demo_events')
        
        # Create events first time
        self.client.post(url)
        first_count = PredictionEvent.objects.filter(source_id='demo').count()
        self.assertEqual(first_count, 4)
        
        # Try to create again - will create new events with different timestamps
        # This is expected behavior as the source_event_id includes timestamp
        self.client.post(url)
        second_count = PredictionEvent.objects.filter(source_id='demo').count()
        
        # Should create 4 more events (8 total) since each has unique timestamp
        self.assertEqual(second_count, 8)

    def test_unauthorized_user_cannot_create(self):
        """Test that non-admin users cannot create demo events."""
        # Create regular user without permissions
        regular_user = User.objects.create_user(
            username='regular',
            password='regular123'
        )
        
        client = Client()
        client.login(username='regular', password='regular123')
        
        url = reverse('admin:demo_add_demo_events')
        response = client.post(url)
        
        # Should be forbidden or redirected
        self.assertIn(response.status_code, [302, 403])
        
        # No demo events should be created
        self.assertEqual(
            PredictionEvent.objects.filter(source_id='demo').count(),
            0
        )

    def test_demo_admin_registered(self):
        """Test that demo pseudo-model is registered in admin."""
        from django.contrib import admin
        
        # Check that DemoPseudoModel is registered
        self.assertIn(DemoPseudoModel, admin.site._registry)
        
        # Get the admin class
        demo_admin = admin.site._registry[DemoPseudoModel]
        self.assertEqual(demo_admin.change_list_template, 'admin/demo/demo_index.html')

    def test_demo_changelist_view(self):
        """Test demo admin changelist view."""
        url = reverse('admin:demo_demopseudomodel_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Demo Events Management')
        self.assertContains(response, 'Create Demo Events')
        self.assertContains(response, 'Current Demo Events')
        
    def test_demo_changelist_shows_event_count(self):
        """Test that changelist displays correct event count."""
        # Create some demo events
        create_url = reverse('admin:demo_add_demo_events')
        self.client.post(create_url)
        
        # Visit changelist
        list_url = reverse('admin:demo_demopseudomodel_changelist')
        response = self.client.get(list_url)
        
        self.assertEqual(response.status_code, 200)
        # Should show 4 demo events
        self.assertContains(response, '4')
        
    def test_demo_appears_in_admin_index(self):
        """Test that demo app appears in admin index."""
        url = reverse('admin:index')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Should contain Demo app section
        self.assertContains(response, 'Demo')
