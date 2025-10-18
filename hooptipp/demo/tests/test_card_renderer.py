"""Tests for demo card renderer."""

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from hooptipp.predictions.models import (
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
    EventOutcome,
)
from hooptipp.demo.card_renderer import DemoCardRenderer


class DemoCardRendererTestCase(TestCase):
    """Test case for demo card renderer."""

    def setUp(self):
        """Set up test fixtures."""
        self.renderer = DemoCardRenderer()
        
        # Create tip type
        now = timezone.now()
        self.tip_type = TipType.objects.create(
            slug='demo-tips',
            name='Demo Tips',
            deadline=now + timedelta(days=7),
        )
        
        # Create option category and options
        self.yesno_cat = OptionCategory.objects.create(
            slug='demo-yesno',
            name='Yes/No',
        )
        
        self.yes_option = Option.objects.create(
            category=self.yesno_cat,
            slug='yes',
            name='Yes',
            short_name='Y',
        )
        
        self.no_option = Option.objects.create(
            category=self.yesno_cat,
            slug='no',
            name='No',
            short_name='N',
        )

    def test_can_render_demo_event(self):
        """Test that renderer can render demo events."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Demo Event',
            source_id='demo',
            source_event_id='test-123',
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        self.assertTrue(self.renderer.can_render(event))

    def test_cannot_render_non_demo_event(self):
        """Test that renderer cannot render non-demo events."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test NBA Event',
            source_id='nba-balldontlie',
            source_event_id='test-456',
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        self.assertFalse(self.renderer.can_render(event))

    def test_get_event_template_yesno(self):
        """Test getting template for yes/no event."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Yes/No',
            source_id='demo',
            source_event_id='test-yesno',
            metadata={'event_type': 'yesno'},
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        template = self.renderer.get_event_template(event)
        self.assertEqual(template, 'demo/cards/yesno.html')

    def test_get_event_template_colors(self):
        """Test getting template for colors event."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Colors',
            source_id='demo',
            source_event_id='test-colors',
            metadata={'event_type': 'colors'},
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        template = self.renderer.get_event_template(event)
        self.assertEqual(template, 'demo/cards/colors.html')

    def test_get_event_template_bonus(self):
        """Test getting template for bonus event."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Bonus',
            source_id='demo',
            source_event_id='test-bonus',
            metadata={'event_type': 'bonus'},
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        template = self.renderer.get_event_template(event)
        self.assertEqual(template, 'demo/cards/bonus.html')

    def test_get_event_template_player(self):
        """Test getting template for player event."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Player',
            source_id='demo',
            source_event_id='test-player',
            metadata={'event_type': 'player'},
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        template = self.renderer.get_event_template(event)
        self.assertEqual(template, 'demo/cards/player.html')

    def test_get_event_template_fallback(self):
        """Test fallback to generic template."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Generic',
            source_id='demo',
            source_event_id='test-generic',
            metadata={},
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        template = self.renderer.get_event_template(event)
        self.assertEqual(template, 'demo/cards/generic.html')

    def test_get_result_template_yesno(self):
        """Test getting result template for yes/no event."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Yes/No',
            source_id='demo',
            source_event_id='test-yesno',
            metadata={'event_type': 'yesno'},
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        outcome = EventOutcome.objects.create(
            prediction_event=event,
            winning_generic_option=self.yes_option,
        )
        
        template = self.renderer.get_result_template(outcome)
        self.assertEqual(template, 'demo/cards/yesno_result.html')

    def test_get_event_context_basic(self):
        """Test getting event context."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Event',
            source_id='demo',
            source_event_id='test-basic',
            metadata={'event_type': 'yesno'},
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        context = self.renderer.get_event_context(event)
        
        self.assertTrue(context['demo'])
        self.assertEqual(context['event_type'], 'yesno')

    def test_get_event_context_colors(self):
        """Test getting event context for colors event."""
        # Create colors category and options
        colors_cat = OptionCategory.objects.create(
            slug='demo-colors',
            name='Colors',
        )
        
        red_option = Option.objects.create(
            category=colors_cat,
            slug='red',
            name='Red',
            metadata={'color': '#ef4444'},
        )
        
        blue_option = Option.objects.create(
            category=colors_cat,
            slug='blue',
            name='Blue',
            metadata={'color': '#3b82f6'},
        )
        
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Colors',
            source_id='demo',
            source_event_id='test-colors',
            metadata={'event_type': 'colors'},
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        # Add prediction options
        PredictionOption.objects.create(
            event=event,
            option=red_option,
            label='Red',
        )
        
        PredictionOption.objects.create(
            event=event,
            option=blue_option,
            label='Blue',
        )
        
        context = self.renderer.get_event_context(event)
        
        self.assertTrue(context['demo'])
        self.assertEqual(context['event_type'], 'colors')
        self.assertIn('colors', context)
        self.assertEqual(context['colors'][red_option.id], '#ef4444')
        self.assertEqual(context['colors'][blue_option.id], '#3b82f6')

    def test_get_event_context_special(self):
        """Test getting event context for special/bonus event."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Bonus',
            source_id='demo',
            source_event_id='test-bonus',
            metadata={'event_type': 'bonus', 'special': True},
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        context = self.renderer.get_event_context(event)
        
        self.assertTrue(context['demo'])
        self.assertTrue(context['special'])

    def test_get_result_context(self):
        """Test getting result context."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Test Result',
            source_id='demo',
            source_event_id='test-result',
            metadata={'event_type': 'yesno'},
            opens_at=timezone.now(),
            deadline=timezone.now() + timedelta(hours=1),
        )
        
        outcome = EventOutcome.objects.create(
            prediction_event=event,
            winning_generic_option=self.yes_option,
        )
        
        context = self.renderer.get_result_context(outcome)
        
        self.assertTrue(context['demo'])
        self.assertEqual(context['event_type'], 'yesno')
        self.assertEqual(context['outcome'], outcome)

    def test_renderer_priority(self):
        """Test that renderer has normal priority."""
        self.assertEqual(self.renderer.priority, 0)
