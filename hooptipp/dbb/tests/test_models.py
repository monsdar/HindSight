"""Tests for DBB models."""

from django.test import TestCase
from django.utils import timezone

from hooptipp.predictions.models import TipType
from hooptipp.dbb.models import DbbMatch, TrackedLeague, TrackedTeam


class TrackedLeagueModelTest(TestCase):
    """Tests for TrackedLeague model."""

    def test_create_tracked_league(self):
        """Test creating a tracked league."""
        league = TrackedLeague.objects.create(
            verband_name='Test Verband',
            verband_id='verband_123',
            league_name='Test League',
            league_id='league_456',
            club_search_term='Test Club',
            is_active=True
        )

        self.assertEqual(league.verband_name, 'Test Verband')
        self.assertEqual(league.league_id, 'league_456')
        self.assertTrue(league.is_active)
        self.assertEqual(str(league), 'Test League (Test Verband)')

    def test_unique_together_constraint(self):
        """Test that verband_id and league_id must be unique together."""
        TrackedLeague.objects.create(
            verband_name='Test Verband',
            verband_id='verband_123',
            league_name='Test League',
            league_id='league_456',
            club_search_term='Test Club'
        )

        # Creating with same verband_id and league_id should raise error
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            TrackedLeague.objects.create(
                verband_name='Test Verband 2',
                verband_id='verband_123',
                league_name='Test League 2',
                league_id='league_456',
                club_search_term='Test Club 2'
            )


class TrackedTeamModelTest(TestCase):
    """Tests for TrackedTeam model."""

    def setUp(self):
        """Set up test data."""
        self.league = TrackedLeague.objects.create(
            verband_name='Test Verband',
            verband_id='verband_123',
            league_name='Test League',
            league_id='league_456',
            club_search_term='Test Club'
        )

    def test_create_tracked_team(self):
        """Test creating a tracked team."""
        team = TrackedTeam.objects.create(
            tracked_league=self.league,
            team_name='BG Test Team',
            team_id='team_789',
            is_active=True
        )

        self.assertEqual(team.team_name, 'BG Test Team')
        self.assertEqual(team.tracked_league, self.league)
        self.assertTrue(team.is_active)
        self.assertIn('BG Test Team', str(team))

    def test_tracked_team_relationship(self):
        """Test relationship between TrackedTeam and TrackedLeague."""
        team1 = TrackedTeam.objects.create(
            tracked_league=self.league,
            team_name='Team 1'
        )
        team2 = TrackedTeam.objects.create(
            tracked_league=self.league,
            team_name='Team 2'
        )

        self.assertEqual(self.league.teams.count(), 2)
        self.assertIn(team1, self.league.teams.all())
        self.assertIn(team2, self.league.teams.all())

    def test_tracked_team_with_logo(self):
        """Test creating a tracked team with a logo."""
        team = TrackedTeam.objects.create(
            tracked_league=self.league,
            team_name='BG Bierden-Bassen',
            logo='bierden-bassen.svg',
            is_active=True
        )

        self.assertEqual(team.logo, 'bierden-bassen.svg')
        self.assertIn('BG Bierden-Bassen', str(team))

    def test_tracked_team_without_logo(self):
        """Test creating a tracked team without a logo (default)."""
        team = TrackedTeam.objects.create(
            tracked_league=self.league,
            team_name='Test Team',
            is_active=True
        )

        self.assertEqual(team.logo, '')
        self.assertIn('Test Team', str(team))


class DbbMatchModelTest(TestCase):
    """Tests for DbbMatch model."""

    def setUp(self):
        """Set up test data."""
        self.tip_type = TipType.objects.create(
            name='DBB Matches',
            slug='dbb-matches',
            category=TipType.TipCategory.GAME,
            deadline=timezone.now()
        )
        
        self.league = TrackedLeague.objects.create(
            verband_name='Test Verband',
            verband_id='verband_123',
            league_name='Test League',
            league_id='league_456',
            club_search_term='Test Club'
        )

    def test_create_dbb_match(self):
        """Test creating a DBB match."""
        match = DbbMatch.objects.create(
            tip_type=self.tip_type,
            external_match_id='match_123',
            match_date=timezone.now(),
            home_team='Home Team',
            away_team='Away Team',
            venue='Test Arena',
            league_name='Test League',
            tracked_league=self.league
        )

        self.assertEqual(match.home_team, 'Home Team')
        self.assertEqual(match.away_team, 'Away Team')
        self.assertEqual(match.league_name, 'Test League')
        self.assertEqual(str(match), 'Home Team vs. Away Team')

    def test_create_dbb_match_without_venue(self):
        """Test creating a DBB match without venue (nullable field)."""
        match = DbbMatch.objects.create(
            tip_type=self.tip_type,
            external_match_id='match_no_venue',
            match_date=timezone.now(),
            home_team='Home Team',
            away_team='Away Team',
            venue=None,
            league_name='Test League'
        )
        
        self.assertEqual(match.home_team, 'Home Team')
        self.assertEqual(match.away_team, 'Away Team')
        self.assertIsNone(match.venue)

    def test_unique_external_match_id(self):
        """Test that external_match_id must be unique."""
        DbbMatch.objects.create(
            tip_type=self.tip_type,
            external_match_id='match_123',
            match_date=timezone.now(),
            home_team='Home Team',
            away_team='Away Team',
            league_name='Test League'
        )

        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            DbbMatch.objects.create(
                tip_type=self.tip_type,
                external_match_id='match_123',
                match_date=timezone.now(),
                home_team='Home Team 2',
                away_team='Away Team 2',
                league_name='Test League 2'
            )

    def test_metadata_field(self):
        """Test metadata JSON field."""
        metadata = {
            'round': 5,
            'match_type': 'regular',
            'officials': ['Ref 1', 'Ref 2']
        }
        
        match = DbbMatch.objects.create(
            tip_type=self.tip_type,
            external_match_id='match_456',
            match_date=timezone.now(),
            home_team='Home Team',
            away_team='Away Team',
            league_name='Test League',
            metadata=metadata
        )

        self.assertEqual(match.metadata['round'], 5)
        self.assertEqual(len(match.metadata['officials']), 2)

