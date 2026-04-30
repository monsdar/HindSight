"""Tests for the NBA admin games functionality."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hooptipp.nba.models import ScheduledGame
from hooptipp.predictions.models import (
    EventOutcome,
    Option,
    OptionCategory,
    PredictionEvent,
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
        # Use naive datetime for the mock to avoid timezone issues
        naive_game_time = game_time.replace(tzinfo=None)
        
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
        mock_game.status = naive_game_time.strftime('%Y-%m-%dT%H:%M:%SZ')  # Status contains datetime
        mock_game.datetime = naive_game_time.isoformat() + 'Z'
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

    @patch('hooptipp.nba.admin._fetch_balldontlie_upcoming')
    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_create_nba_events_view(self, mock_build_client, mock_fetch_upcoming):
        """Test creating prediction events from selected games."""
        mock_build_client.return_value = MagicMock()
        mock_fetch_upcoming.return_value = ([], {'12345'})
        
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
        # Use naive datetime for the mock to avoid timezone issues
        naive_game_time = game_time.replace(tzinfo=None)
        game_data = {
            'game_id': '12345',
            'game_time': naive_game_time.isoformat() + 'Z',
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
        mock_build_client.return_value = MagicMock()
        url = reverse('admin:nba_create_events')
        response = self.client.post(url, {
            'selected_games': [],
        })
        
        self.assertEqual(response.status_code, 302)
        # Should redirect back to the add games page
        self.assertIn('add-upcoming', response.url)

    @patch('hooptipp.nba.admin._fetch_balldontlie_upcoming')
    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_create_nba_events_updates_existing(self, mock_build_client, mock_fetch_upcoming):
        """Selecting an existing BDL-linked event updates deadlines and ScheduledGame."""
        mock_build_client.return_value = MagicMock()
        mock_fetch_upcoming.return_value = ([], {'12345'})
        
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

        game_time = timezone.now() + timedelta(days=2)

        tip_type = TipType.objects.create(
            slug='weekly-games',
            name='Weekly games',
            category=TipType.TipCategory.GAME,
            deadline=timezone.now() + timedelta(days=7),
            is_active=True,
        )

        opens_at_existing = timezone.now()
        naive_game_time = game_time.replace(tzinfo=None)
        scheduled_game = ScheduledGame.objects.create(
            tip_type=tip_type,
            nba_game_id='12345',
            game_date=timezone.make_aware(naive_game_time),
            home_team='Los Angeles Lakers',
            home_team_tricode='LAL',
            away_team='Boston Celtics',
            away_team_tricode='BOS',
            venue='Old Arena',
        )

        existing_event = PredictionEvent.objects.create(
            tip_type=tip_type,
            scheduled_game=scheduled_game,
            name='BOS @ LAL',
            description='Boston Celtics at Los Angeles Lakers',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='nba-balldontlie',
            source_event_id='12345',
            opens_at=opens_at_existing,
            deadline=game_time,
            reveal_at=opens_at_existing,
            points=1,
        )
        
        naive_new_time = (game_time + timedelta(days=3)).replace(tzinfo=None)

        # Try syncing the event with rescheduled kickoff
        game_data = {
            'game_id': '12345',
            'game_time': naive_new_time.isoformat() + 'Z',
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

        events = PredictionEvent.objects.filter(source_event_id='12345')
        self.assertEqual(events.count(), 1)
        updated = events.first()
        self.assertEqual(updated.id, existing_event.id)
        self.assertNotEqual(updated.deadline, game_time)
        self.assertEqual(updated.metadata.get('arena'), 'Crypto.com Arena')
        sg = ScheduledGame.objects.get(nba_game_id='12345')
        self.assertEqual(sg.venue, 'Crypto.com Arena')
        self.assertNotEqual(sg.game_date, game_time)

    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_orphan_events_listed_when_missing_from_feed(self, mock_build_client):
        """Shows orphan section when prediction events lack a BallDontLie feed row."""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.nba.games.list.return_value = mock_response

        tip_type = TipType.objects.create(
            slug='weekly-games',
            name='Weekly games',
            category=TipType.TipCategory.GAME,
            deadline=timezone.now() + timedelta(days=7),
            is_active=True,
        )

        deadline_dt = timezone.now().replace(second=0, microsecond=0) + timedelta(days=5)

        scheduled_game = ScheduledGame.objects.create(
            tip_type=tip_type,
            nba_game_id='99999',
            game_date=deadline_dt,
            home_team='Phoenix Suns',
            home_team_tricode='PHX',
            away_team='Dallas Mavericks',
            away_team_tricode='DAL',
            venue='Away',
        )
        PredictionEvent.objects.create(
            tip_type=tip_type,
            scheduled_game=scheduled_game,
            name='DAL @ PHX',
            description='DAL at PHX',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='nba-balldontlie',
            source_event_id='99999',
            opens_at=timezone.now(),
            deadline=deadline_dt,
            reveal_at=timezone.now(),
            points=1,
        )

        url = reverse('admin:nba_add_upcoming_games')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'orphaned prediction event')

    @patch('hooptipp.nba.admin._fetch_balldontlie_upcoming')
    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_remove_orphan_prediction_event_via_post(self, mock_build_client, mock_fetch_upcoming):
        mock_build_client.return_value = MagicMock()
        mock_fetch_upcoming.return_value = ([], set())

        tip_type = TipType.objects.create(
            slug='weekly-games',
            name='Weekly games',
            category=TipType.TipCategory.GAME,
            deadline=timezone.now() + timedelta(days=7),
            is_active=True,
        )

        deadline_dt = timezone.now().replace(second=0, microsecond=0) + timedelta(days=10)

        scheduled_game = ScheduledGame.objects.create(
            tip_type=tip_type,
            nba_game_id='88888',
            game_date=deadline_dt,
            home_team='Houston Rockets',
            home_team_tricode='HOU',
            away_team='Utah Jazz',
            away_team_tricode='UTA',
            venue='Away',
        )
        orphan = PredictionEvent.objects.create(
            tip_type=tip_type,
            scheduled_game=scheduled_game,
            name='UTA @ HOU',
            description='UTA at HOU',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='nba-balldontlie',
            source_event_id='88888',
            opens_at=timezone.now(),
            deadline=deadline_dt,
            reveal_at=timezone.now(),
            points=1,
        )

        url = reverse('admin:nba_create_events')
        response = self.client.post(url, {'remove_event_ids': [str(orphan.id)]})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(PredictionEvent.objects.filter(pk=orphan.id).count(), 0)
        self.assertEqual(ScheduledGame.objects.filter(pk=scheduled_game.pk).count(), 0)

    @patch('hooptipp.nba.admin._fetch_balldontlie_upcoming')
    @patch('hooptipp.nba.admin._build_bdl_client')
    def test_remove_skips_when_outcome_already_scored(self, mock_build_client, mock_fetch_upcoming):
        mock_build_client.return_value = MagicMock()
        mock_fetch_upcoming.return_value = ([], set())

        tip_type = TipType.objects.create(
            slug='weekly-games',
            name='Weekly games',
            category=TipType.TipCategory.GAME,
            deadline=timezone.now() + timedelta(days=7),
            is_active=True,
        )

        deadline_dt = timezone.now().replace(second=0, microsecond=0) + timedelta(days=15)

        scheduled_game = ScheduledGame.objects.create(
            tip_type=tip_type,
            nba_game_id='77777',
            game_date=deadline_dt,
            home_team='Memphis Grizzlies',
            home_team_tricode='MEM',
            away_team='Oklahoma City Thunder',
            away_team_tricode='OKC',
            venue='Away',
        )
        scored_event = PredictionEvent.objects.create(
            tip_type=tip_type,
            scheduled_game=scheduled_game,
            name='OKC @ MEM',
            description='OKC at MEM',
            target_kind=PredictionEvent.TargetKind.TEAM,
            selection_mode=PredictionEvent.SelectionMode.CURATED,
            source_id='nba-balldontlie',
            source_event_id='77777',
            opens_at=timezone.now(),
            deadline=deadline_dt,
            reveal_at=timezone.now(),
            points=1,
        )
        EventOutcome.objects.create(prediction_event=scored_event, scored_at=timezone.now())

        url = reverse('admin:nba_create_events')
        response = self.client.post(url, {'remove_event_ids': [str(scored_event.id)]})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(PredictionEvent.objects.filter(pk=scored_event.id).exists())

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
