"""Tests for the ``print_season_stats`` management command."""

from __future__ import annotations

from datetime import timedelta
from datetime import time as time_type
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from hooptipp.predictions.management.commands.print_season_stats import resolve_latest_finished_season
from hooptipp.predictions.models import (
    EventOutcome,
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    Season,
    TipType,
    UserEventScore,
    UserTip,
)

User = get_user_model()


class PrintSeasonStatsCommandTests(TestCase):
    """Integration tests for ``print_season_stats``."""

    def setUp(self) -> None:
        self.now = timezone.now()
        self.season_older = Season.objects.create(
            name="Older Finished Season",
            start_date=(self.now - timedelta(days=120)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(self.now - timedelta(days=100)).date(),
            end_time=time_type(23, 59, 59),
        )
        self.season_latest = Season.objects.create(
            name="Latest Finished Season",
            start_date=(self.now - timedelta(days=45)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(self.now - timedelta(days=30)).date(),
            end_time=time_type(23, 59, 59),
        )
        self.tip_type = TipType.objects.create(
            name="Stats Cmd Tip Type",
            slug="stats-cmd-tip-type",
            deadline=self.now + timedelta(days=1),
        )
        self.category = OptionCategory.objects.create(
            slug="stats-cmd-category",
            name="Stats Cmd Category",
        )
        self.option_winner = Option.objects.create(
            category=self.category,
            slug="stats-cmd-winner",
            name="Winner Team",
        )
        self.option_loser = Option.objects.create(
            category=self.category,
            slug="stats-cmd-loser",
            name="Loser Team",
        )

        deadline = self.now - timedelta(days=35)
        opens = deadline - timedelta(days=2)
        self.event = PredictionEvent.objects.create(
            tip_type=self.tip_type,
            name="Test Match",
            opens_at=opens,
            deadline=deadline,
            reveal_at=opens,
        )
        self.po_winner = PredictionOption.objects.create(
            event=self.event,
            option=self.option_winner,
            label=self.option_winner.name,
            sort_order=1,
        )
        self.po_loser = PredictionOption.objects.create(
            event=self.event,
            option=self.option_loser,
            label=self.option_loser.name,
            sort_order=2,
        )

        self.user_winner = User.objects.create_user(username="stats_winner", password="pass")
        self.user_loser = User.objects.create_user(username="stats_loser", password="pass")

        UserTip.objects.create(
            user=self.user_winner,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.po_winner,
            selected_option=self.option_winner,
            prediction=self.po_winner.label,
        )
        UserTip.objects.create(
            user=self.user_loser,
            tip_type=self.tip_type,
            prediction_event=self.event,
            prediction_option=self.po_loser,
            selected_option=self.option_loser,
            prediction=self.po_loser.label,
        )

        self.outcome = EventOutcome.objects.create(
            prediction_event=self.event,
            winning_option=self.po_winner,
            winning_generic_option=self.option_winner,
        )

        UserEventScore.objects.create(
            user=self.user_winner,
            prediction_event=self.event,
            base_points=1,
            lock_multiplier=1,
            points_awarded=1,
            awarded_at=self.now - timedelta(days=34),
        )

    def test_resolve_latest_finished_season(self) -> None:
        resolved = resolve_latest_finished_season()
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.pk, self.season_latest.pk)

    def test_default_prints_latest_season_name(self) -> None:
        out = StringIO()
        call_command("print_season_stats", "--min-settled", "1", "--top", "5", stdout=out)
        text = out.getvalue()
        self.assertIn("Latest Finished Season", text)
        self.assertIn("stats_winner", text)
        self.assertIn("stats_loser", text)
        self.assertIn("1/1 (100.0%)", text)
        self.assertIn("0/1 (0.0%)", text)

    def test_season_id_selects_other_season(self) -> None:
        out = StringIO()
        call_command(
            "print_season_stats",
            "--season-id",
            str(self.season_older.pk),
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("Older Finished Season", text)
        self.assertNotIn("Latest Finished Season", text)

    def test_invalid_season_id_raises(self) -> None:
        with self.assertRaises(CommandError):
            call_command("print_season_stats", "--season-id", "999999")

    def test_no_finished_season_raises(self) -> None:
        Season.objects.all().delete()
        Season.objects.create(
            name="Only Future Season",
            start_date=(self.now + timedelta(days=10)).date(),
            start_time=time_type(0, 0, 0),
            end_date=(self.now + timedelta(days=20)).date(),
            end_time=time_type(23, 59, 59),
        )
        with self.assertRaises(CommandError):
            call_command("print_season_stats")
