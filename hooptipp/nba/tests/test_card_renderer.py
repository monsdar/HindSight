"""Tests for NBA card renderer."""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from hooptipp.nba.card_renderer import NbaCardRenderer
from hooptipp.predictions.models import (
    EventOutcome,
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    ScheduledGame,
    TipType,
)


class NbaCardRendererTests(TestCase):
    """Tests for NbaCardRenderer."""

    def setUp(self):
        self.renderer = NbaCardRenderer()
        self.User = get_user_model()
        self.user = self.User.objects.create_user(username="testuser")

        self.tip_type = TipType.objects.create(
            name="Weekly games",
            slug="weekly-games",
            deadline=timezone.now(),
        )

        # Create NBA teams category and options
        self.teams_cat = OptionCategory.objects.create(
            slug="nba-teams",
            name="NBA Teams",
        )
        self.lakers_option = Option.objects.create(
            category=self.teams_cat,
            slug="lal",
            name="Los Angeles Lakers",
            short_name="LAL",
            external_id="1",
        )
        self.celtics_option = Option.objects.create(
            category=self.teams_cat,
            slug="bos",
            name="Boston Celtics",
            short_name="BOS",
            external_id="2",
        )

    def test_can_render_nba_events(self):
        """Renderer should accept NBA events."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="LAL @ BOS",
            source_id="nba-balldontlie",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        self.assertTrue(self.renderer.can_render(event))

    def test_cannot_render_non_nba_events(self):
        """Renderer should reject non-NBA events."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Other Event",
            source_id="other-source",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        self.assertFalse(self.renderer.can_render(event))

    def test_get_event_template_for_game(self):
        """Renderer should return game template for game events."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="LAL @ BOS",
            source_id="nba-balldontlie",
            metadata={"event_type": "game"},
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        template = self.renderer.get_event_template(event)
        self.assertEqual(template, "nba/cards/game.html")

    def test_get_event_template_for_mvp(self):
        """Renderer should return MVP template for MVP events."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="MVP Prediction",
            source_id="nba-balldontlie",
            metadata={"event_type": "mvp"},
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        template = self.renderer.get_event_template(event)
        self.assertEqual(template, "nba/cards/mvp.html")

    def test_get_event_template_for_playoff_series(self):
        """Renderer should return playoff template for playoff events."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Playoff Series",
            source_id="nba-balldontlie",
            metadata={"event_type": "playoff_series"},
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        template = self.renderer.get_event_template(event)
        self.assertEqual(template, "nba/cards/playoff_series.html")

    def test_get_event_template_default(self):
        """Renderer should default to game template."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Default Event",
            source_id="nba-balldontlie",
            metadata={},
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        template = self.renderer.get_event_template(event)
        self.assertEqual(template, "nba/cards/game.html")

    def test_get_result_template_for_game(self):
        """Renderer should return game result template."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="LAL @ BOS",
            source_id="nba-balldontlie",
            metadata={"event_type": "game"},
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )
        pred_option = PredictionOption.objects.create(
            event=event,
            label="Lakers",
            option=self.lakers_option,
        )
        outcome = EventOutcome.objects.create(
            prediction_event=event,
            winning_option=pred_option,
        )

        template = self.renderer.get_result_template(outcome)
        self.assertEqual(template, "nba/cards/game_result.html")

    def test_get_event_context_for_game(self):
        """Renderer should provide game context with team data."""
        game_time = timezone.now() + timedelta(hours=2)
        game = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id="GAME123",
            game_date=game_time,
            home_team="Los Angeles Lakers",
            home_team_tricode="LAL",
            away_team="Boston Celtics",
            away_team_tricode="BOS",
            venue="Crypto.com Arena",
        )

        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="BOS @ LAL",
            source_id="nba-balldontlie",
            scheduled_game=game,
            opens_at=timezone.now(),
            deadline=game_time,
        )

        context = self.renderer.get_event_context(event)

        # Check team data
        self.assertEqual(context["home_team"], "Los Angeles Lakers")
        self.assertEqual(context["home_team_tricode"], "LAL")
        self.assertEqual(context["away_team"], "Boston Celtics")
        self.assertEqual(context["away_team_tricode"], "BOS")
        self.assertEqual(context["venue"], "Crypto.com Arena")
        self.assertEqual(context["game_time"], game_time)

        # Check team logos are provided
        self.assertIn("home_team_logo", context)
        self.assertIn("away_team_logo", context)
        self.assertIn("LAL", context["home_team_logo"])
        self.assertIn("BOS", context["away_team_logo"])

    def test_get_event_context_with_playoff_data(self):
        """Renderer should include playoff context if available."""
        game_time = timezone.now() + timedelta(hours=2)
        game = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id="PLAYOFF123",
            game_date=game_time,
            home_team="Los Angeles Lakers",
            home_team_tricode="LAL",
            away_team="Boston Celtics",
            away_team_tricode="BOS",
        )

        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Finals Game 1",
            source_id="nba-balldontlie",
            scheduled_game=game,
            metadata={
                "event_type": "game",
                "playoff_series": {
                    "name": "NBA Finals",
                    "game_number": 1,
                    "series_score": "LAL 0-0 BOS",
                },
            },
            opens_at=timezone.now(),
            deadline=game_time,
        )

        context = self.renderer.get_event_context(event)

        # Check playoff context
        self.assertIn("playoff_context", context)
        self.assertEqual(context["playoff_context"]["series_name"], "NBA Finals")
        self.assertEqual(context["playoff_context"]["game_number"], 1)
        self.assertEqual(context["playoff_context"]["series_score"], "LAL 0-0 BOS")

    def test_get_event_context_for_mvp(self):
        """Renderer should provide player data for MVP events."""
        # Create players category
        players_cat = OptionCategory.objects.create(
            slug="nba-players",
            name="NBA Players",
        )
        lebron = Option.objects.create(
            category=players_cat,
            slug="lebron-james",
            name="LeBron James",
            external_id="123",
            metadata={
                "position": "F",
                "team_name": "Los Angeles Lakers",
                "team_abbreviation": "LAL",
            },
        )

        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="MVP Prediction",
            source_id="nba-balldontlie",
            metadata={"event_type": "mvp"},
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )
        PredictionOption.objects.create(
            event=event,
            label="LeBron James",
            option=lebron,
        )

        with mock.patch("hooptipp.nba.card_renderer.get_player_card_data") as mock_get_player:
            mock_get_player.return_value = {
                "portrait_url": None,
                "team": "Los Angeles Lakers",
                "team_tricode": "LAL",
                "position": "F",
                "current_stats": None,
            }

            context = self.renderer.get_event_context(event)

            # Check players data structure
            self.assertIn("players", context)
            self.assertIsInstance(context["players"], dict)

            # Check MVP standings (empty by default)
            self.assertIn("mvp_standings", context)

    def test_get_event_context_with_live_game(self):
        """Renderer should fetch live data for in-progress games."""
        game_time = timezone.now() - timedelta(hours=1)
        game = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id="LIVE123",
            game_date=game_time,
            home_team="Los Angeles Lakers",
            home_team_tricode="LAL",
            away_team="Boston Celtics",
            away_team_tricode="BOS",
        )

        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="BOS @ LAL",
            source_id="nba-balldontlie",
            scheduled_game=game,
            metadata={"status": "in_progress"},
            opens_at=timezone.now() - timedelta(hours=2),
            deadline=game_time,
        )

        with mock.patch("hooptipp.nba.card_renderer.get_live_game_data") as mock_live:
            mock_live.return_value = {
                "away_score": 95,
                "home_score": 98,
                "game_status": "Q3 5:23",
                "is_live": True,
            }

            context = self.renderer.get_event_context(event)

            # Check live data
            self.assertEqual(context["away_score"], 95)
            self.assertEqual(context["home_score"], 98)
            self.assertEqual(context["game_status"], "Q3 5:23")
            self.assertTrue(context["is_live"])

    def test_get_result_context_includes_final_score(self):
        """Renderer should fetch final score for result cards."""
        game_time = timezone.now() - timedelta(hours=2)
        game = ScheduledGame.objects.create(
            tip_type=self.tip_type,
            nba_game_id="FINAL123",
            game_date=game_time,
            home_team="Los Angeles Lakers",
            home_team_tricode="LAL",
            away_team="Boston Celtics",
            away_team_tricode="BOS",
        )

        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="BOS @ LAL",
            source_id="nba-balldontlie",
            scheduled_game=game,
            opens_at=timezone.now() - timedelta(days=1),
            deadline=game_time,
        )
        pred_option = PredictionOption.objects.create(
            event=event,
            label="Lakers",
            option=self.lakers_option,
        )
        outcome = EventOutcome.objects.create(
            prediction_event=event,
            winning_option=pred_option,
        )

        with mock.patch("hooptipp.nba.services.get_live_game_data") as mock_live:
            mock_live.return_value = {
                "away_score": 105,
                "home_score": 110,
                "game_status": "Final",
                "is_live": False,
            }

            context = self.renderer.get_result_context(outcome)

            # Check final score data
            self.assertEqual(context["away_score"], 105)
            self.assertEqual(context["home_score"], 110)
            self.assertEqual(context["game_status"], "Final")

    def test_renderer_priority(self):
        """Renderer should have default priority."""
        self.assertEqual(self.renderer.priority, 0)

    def test_get_event_context_without_scheduled_game(self):
        """Renderer should handle events without scheduled games."""
        event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Test Event",
            source_id="nba-balldontlie",
            opens_at=timezone.now(),
            deadline=timezone.now(),
        )

        context = self.renderer.get_event_context(event)

        # Should return empty context without errors
        self.assertEqual(context, {})
