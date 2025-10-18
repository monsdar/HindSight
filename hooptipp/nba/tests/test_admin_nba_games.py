"""Tests for the NBA admin games functionality."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hooptipp.nba.models import ScheduledGame
from hooptipp.predictions.models import (
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
)


User = get_user_model()


class AddNbaGamesAdminViewTest(TestCase):
    """Test the admin view for adding NBA games."""

    def setUp(self):
        """Set up test fixtures."""
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123',
        )
        self.client.force_login(self.admin_user)
        
        # Create NBA teams category
        self.teams_category, _ = OptionCategory.objects.get_or_create(
            slug='nba-teams',
            defaults={
                'name': 'NBA Teams',
                'description': 'NBA teams',
                'icon': 'basketball',
            },
        )

    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_add_nba_games_view_no_client(self, mock_build_client):
        """Test the view when BallDontLie client is not configured."""
        mock_build_client.return_value = None
        
        url = reverse('admin:nba_add_upcoming_games')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('balldontlie api is not configured', 
                      str(response.wsgi_request._messages._queued_messages[0].message).lower())

    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_add_nba_games_view_success(self, mock_build_client):
        """Test successful fetching of games."""
        # Mock the BallDontLie API response
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Create mock game data
        game_time = timezone.now() + timedelta(days=2)
        
        mock_home_team = MagicMock()
        mock_home_team.id = 1
        mock_home_team.full_name = 'Los Angeles Lakers'
        mock_home_team.name = 'Lakers'
        mock_home_team.abbreviation = 'LAL'
        mock_home_team.city = 'Los Angeles'
        mock_home_team.conference = 'West'
        mock_home_team.division = 'Pacific'
        
        mock_away_team = MagicMock()
        mock_away_team.id = 2
        mock_away_team.full_name = 'Boston Celtics'
        mock_away_team.name = 'Celtics'
        mock_away_team.abbreviation = 'BOS'
        mock_away_team.city = 'Boston'
        mock_away_team.conference = 'East'
        mock_away_team.division = 'Atlantic'
        
        mock_game = MagicMock()
        mock_game.id = 12345
        mock_game.status = 'Scheduled'
        mock_game.date = game_time.isoformat()
        mock_game.home_team = mock_home_team
        mock_game.visitor_team = mock_away_team
        mock_game.arena = 'Crypto.com Arena'
        
        mock_response = MagicMock()
        mock_response.data = [mock_game]
        mock_client.nba.games.list.return_value = mock_response
        
        url = reverse('admin:nba_add_upcoming_games')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Add Upcoming NBA Games', response.content)
        self.assertIn(b'BOS @ LAL', response.content)
        self.assertContains(response, 'Boston Celtics at Los Angeles Lakers')

    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_create_nba_events_view(self, mock_build_client):
        """Test creating prediction events from selected games."""
        from hooptipp.predictions.models import Option
        
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Create tip type
        tip_type = TipType.objects.create(
            slug='weekly-games',
            name='Weekly games',
            category=TipType.TipCategory.GAME,
            deadline=timezone.now() + timedelta(days=7),
            is_active=True,
        )
        
        # Create team options that will be found by abbreviation
        Option.objects.create(
            category=self.teams_category,
            slug='lal',
            name='Los Angeles Lakers',
            short_name='LAL',
            external_id='1',
            metadata={'city': 'Los Angeles', 'conference': 'West', 'division': 'Pacific'}
        )
        Option.objects.create(
            category=self.teams_category,
            slug='bos',
            name='Boston Celtics',
            short_name='BOS',
            external_id='2',
            metadata={'city': 'Boston', 'conference': 'East', 'division': 'Atlantic'}
        )
        
        # Create game data
        game_time = timezone.now() + timedelta(days=2)
        game_data = {
            'game_id': '12345',
            'game_time': game_time.isoformat(),
            'home_team': {
                'id': 1,
                'full_name': 'Los Angeles Lakers',
                'name': 'Lakers',
                'abbreviation': 'LAL',
                'city': 'Los Angeles',
                'conference': 'West',
                'division': 'Pacific',
            },
            'away_team': {
                'id': 2,
                'full_name': 'Boston Celtics',
                'name': 'Celtics',
                'abbreviation': 'BOS',
                'city': 'Boston',
                'conference': 'East',
                'division': 'Atlantic',
            },
            'arena': 'Crypto.com Arena',
        }
        
        import json
        url = reverse('admin:nba_create_events')
        response = self.client.post(url, {
            'selected_games': ['12345'],
            'game_data_12345': json.dumps(game_data),
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Verify event was created
        event = PredictionEvent.objects.filter(source_event_id='12345').first()
        self.assertIsNotNone(event)
        self.assertEqual(event.name, 'BOS @ LAL')
        self.assertEqual(event.deadline, game_time)
        
        # Verify opens_at is 1 week before game time (or now if that's later)
        expected_opens_at = game_time - timedelta(days=7)
        if expected_opens_at < timezone.now():
            expected_opens_at = timezone.now()
        
        # Allow for small time differences in test execution
        time_diff = abs((event.opens_at - expected_opens_at).total_seconds())
        self.assertLess(time_diff, 60)  # Within 1 minute

    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_create_nba_events_no_games_selected(self, mock_build_client):
        """Test creating events with no games selected."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        url = reverse('admin:nba_create_events')
        response = self.client.post(url, {
            'selected_games': [],
        })
        
        self.assertEqual(response.status_code, 302)
        # Should redirect back to the add games page
        self.assertIn('add-upcoming', response.url)

    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_create_nba_events_skip_existing(self, mock_build_client):
        """Test that existing events are skipped."""
        from hooptipp.predictions.models import Option
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Create team options
        Option.objects.create(
            category=self.teams_category,
            slug='lal',
            name='Los Angeles Lakers',
            short_name='LAL',
            external_id='1',
            metadata={'city': 'Los Angeles', 'conference': 'West', 'division': 'Pacific'}
        )
        Option.objects.create(
            category=self.teams_category,
            slug='bos',
            name='Boston Celtics',
            short_name='BOS',
            external_id='2',
            metadata={'city': 'Boston', 'conference': 'East', 'division': 'Atlantic'}
        )
        
        # Create an existing event
        tip_type = TipType.objects.create(
            slug='weekly-games',
            name='Weekly games',
            category=TipType.TipCategory.GAME,
            deadline=timezone.now() + timedelta(days=7),
            is_active=True,
        )
        
        game_time = timezone.now() + timedelta(days=2)
        
        existing_event = PredictionEvent.objects.create(
            tip_type=tip_type,
            name='BOS @ LAL',
            source_id='nba-balldontlie',
            source_event_id='12345',
            opens_at=timezone.now(),
            deadline=game_time,
        )
        
        # Try to create the same event again
        game_data = {
            'game_id': '12345',
            'game_time': game_time.isoformat(),
            'home_team': {
                'id': 1,
                'full_name': 'Los Angeles Lakers',
                'abbreviation': 'LAL',
            },
            'away_team': {
                'id': 2,
                'full_name': 'Boston Celtics',
                'abbreviation': 'BOS',
            },
            'arena': 'Crypto.com Arena',
        }
        
        import json
        url = reverse('admin:nba_create_events')
        response = self.client.post(url, {
            'selected_games': ['12345'],
            'game_data_12345': json.dumps(game_data),
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Verify only one event exists
        events = PredictionEvent.objects.filter(source_event_id='12345')
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().id, existing_event.id)

    def test_admin_permissions(self):
        """Test that non-admin users cannot access the views."""
        # Create a regular user
        regular_user = User.objects.create_user(
            username='regular',
            email='regular@test.com',
            password='testpass123',
        )
        self.client.force_login(regular_user)
        
        url = reverse('admin:nba_add_upcoming_games')
        response = self.client.get(url)
        
        # Should redirect to login or show permission denied
        self.assertIn(response.status_code, [302, 403])
