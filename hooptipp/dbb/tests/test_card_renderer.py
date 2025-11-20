"""Tests for DBB card renderer."""

import tempfile
from pathlib import Path

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
from hooptipp.dbb.card_renderer import DbbCardRenderer


class DbbCardRendererTest(TestCase):
    """Tests for DbbCardRenderer."""

    def setUp(self):
        """Set up test data."""
        self.renderer = DbbCardRenderer()
        
        # Create tip type
        self.tip_type = TipType.objects.create(
            name='DBB Matches',
            slug='dbb-matches',
            category=TipType.TipCategory.GAME,
            deadline=timezone.now()
        )
        
        # Create option category and teams
        self.category = OptionCategory.objects.create(
            slug='dbb-teams',
            name='German Basketball Teams'
        )
        
        self.team1 = Option.objects.create(
            category=self.category,
            slug='team-1',
            name='Team 1',
            short_name='T1'
        )
        
        self.team2 = Option.objects.create(
            category=self.category,
            slug='team-2',
            name='Team 2',
            short_name='T2'
        )
        
        # Create prediction event
        self.event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Team 1 @ Team 2',
            description='Test match',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='dbb-slapi',
            source_event_id='match_123',
            metadata={
                'league_name': 'Test League',
                'verband_name': 'Test Verband',
                'venue': 'Test Arena'
            },
            opens_at=timezone.now(),
            deadline=timezone.now() + timezone.timedelta(days=7),
            reveal_at=timezone.now(),
            is_active=True
        )
        
        # Create prediction options
        self.option1 = PredictionOption.objects.create(
            event=self.event,
            option=self.team1,
            label='Team 1',
            sort_order=1,
            is_active=True
        )
        
        self.option2 = PredictionOption.objects.create(
            event=self.event,
            option=self.team2,
            label='Team 2',
            sort_order=2,
            is_active=True
        )

    def test_can_render(self):
        """Test that renderer matches DBB events."""
        self.assertTrue(self.renderer.can_render(self.event))
        
        # Test with non-DBB event
        other_event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name='Other Event',
            source_id='other-source',
            opens_at=timezone.now(),
            deadline=timezone.now() + timezone.timedelta(days=7),
            reveal_at=timezone.now()
        )
        self.assertFalse(self.renderer.can_render(other_event))

    def test_get_event_template(self):
        """Test getting event template."""
        template = self.renderer.get_event_template(self.event)
        self.assertEqual(template, 'dbb/cards/match.html')

    def test_get_result_template(self):
        """Test getting result template."""
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.option1,
            winning_generic_option=self.team1,
            metadata={'home_score': 85, 'away_score': 78}
        )
        
        template = self.renderer.get_result_template(outcome)
        self.assertEqual(template, 'dbb/cards/match_result.html')

    def test_get_event_context(self):
        """Test getting event context data."""
        context = self.renderer.get_event_context(self.event)
        
        self.assertEqual(context['league_name'], 'Test League')
        self.assertEqual(context['verband_name'], 'Test Verband')
        self.assertEqual(context['venue'], 'Test Arena')
        self.assertIn('away_team', context)
        self.assertIn('home_team', context)
        self.assertIn('away_team_option_id', context)
        self.assertIn('home_team_option_id', context)

    def test_get_result_context(self):
        """Test getting result context data."""
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.option1,
            winning_generic_option=self.team1,
            metadata={
                'home_score': 85,
                'away_score': 78,
                'match_status': 'Final'
            }
        )
        
        context = self.renderer.get_result_context(outcome)
        
        self.assertEqual(context['home_score'], 85)
        self.assertEqual(context['away_score'], 78)
        self.assertEqual(context['match_status'], 'Final')
        self.assertIn('league_name', context)

    def test_priority(self):
        """Test renderer priority."""
        self.assertEqual(self.renderer.priority, 0)

    def test_get_event_context_with_logos(self):
        """Test that logos are included in event context when available."""
        # Add logos to team metadata
        self.team1.metadata = {'logo': 'team1.svg'}
        self.team1.save()
        
        self.team2.metadata = {'logo': 'team2.svg'}
        self.team2.save()
        
        # Refresh the prediction options to get updated option data
        self.option1.refresh_from_db()
        self.option2.refresh_from_db()
        
        context = self.renderer.get_event_context(self.event)
        
        self.assertEqual(context['away_team_logo'], 'team1.svg')
        self.assertEqual(context['home_team_logo'], 'team2.svg')

    def test_get_event_context_without_logos(self):
        """Test that empty strings are returned when logos are not available."""
        context = self.renderer.get_event_context(self.event)
        
        # Should have empty logo fields when no logo is set
        self.assertEqual(context.get('away_team_logo', ''), '')
        self.assertEqual(context.get('home_team_logo', ''), '')

    def test_get_result_context_with_logos(self):
        """Test that logos are included in result context."""
        # Add logos to team metadata
        self.team1.metadata = {'logo': 'team1.svg'}
        self.team1.save()
        
        self.team2.metadata = {'logo': 'team2.svg'}
        self.team2.save()
        
        outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.option1,
            winning_generic_option=self.team1,
            metadata={
                'home_score': 85,
                'away_score': 78,
                'match_status': 'Final'
            }
        )
        
        context = self.renderer.get_result_context(outcome)
        
        # Result context should include logos from event context
        self.assertEqual(context.get('away_team_logo', ''), 'team1.svg')
        self.assertEqual(context.get('home_team_logo', ''), 'team2.svg')

    def test_dynamic_logo_discovery_at_render_time(self):
        """Test that logos are discovered dynamically when rendering, even without metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test static/dbb directory with logos
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            (static_dbb / 'team-1.svg').touch()
            (static_dbb / 'team-2.svg').touch()
            
            with override_settings(BASE_DIR=tmpdir):
                # Teams don't have logos in metadata
                self.assertIsNone(self.team1.metadata.get('logo') if self.team1.metadata else None)
                self.assertIsNone(self.team2.metadata.get('logo') if self.team2.metadata else None)
                
                # But logos should be discovered dynamically at render time
                context = self.renderer.get_event_context(self.event)
                
                # Logos should be auto-discovered based on team names
                self.assertEqual(context['away_team_logo'], 'team-1.svg')
                self.assertEqual(context['home_team_logo'], 'team-2.svg')

    def test_metadata_logo_takes_precedence_over_dynamic_discovery(self):
        """Test that logos in metadata take precedence over dynamic discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test static/dbb directory with auto-discoverable logos
            static_dbb = Path(tmpdir) / 'static' / 'dbb'
            static_dbb.mkdir(parents=True)
            (static_dbb / 'team-1.svg').touch()  # Auto-discoverable
            
            # Set a different logo in metadata
            self.team1.metadata = {'logo': 'manual-logo.svg'}
            self.team1.save()
            
            with override_settings(BASE_DIR=tmpdir):
                context = self.renderer.get_event_context(self.event)
                
                # Manual logo from metadata should be used, not auto-discovered one
                self.assertEqual(context['away_team_logo'], 'manual-logo.svg')

