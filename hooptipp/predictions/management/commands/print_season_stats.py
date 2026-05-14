"""
Print aggregated statistics for a prediction season (read-only).

Uses the same season window semantics as the scoreboard: tips are filtered by
``PredictionEvent.deadline``; points are filtered by ``UserEventScore.awarded_at``.
Correct picks use ``scoring_service._tip_matches_outcome`` (excluding forfeited outcomes).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Sum
from django.utils import timezone

from hooptipp.predictions.models import (
    Achievement,
    EventOutcome,
    HotnessKudos,
    PredictionEvent,
    Season,
    SeasonParticipant,
    UserEventScore,
    UserHotness,
    UserTip,
)
from hooptipp.predictions.scoring_service import (
    _is_forfeited_match,
    _tip_matches_outcome,
)

User = get_user_model()


def resolve_latest_finished_season() -> Season | None:
    """Return the finished season with the greatest ``end_datetime``, if any."""
    now = timezone.now()
    best: Season | None = None
    best_end = None
    for season in (
        Season.objects.exclude(start_date__isnull=True)
        .exclude(end_date__isnull=True)
        .order_by("-end_date", "-end_time", "-id")
    ):
        try:
            end_dt = season.end_datetime
        except (ValueError, AttributeError):
            continue
        if end_dt >= now:
            continue
        if best is None or end_dt > best_end:
            best = season
            best_end = end_dt
    return best


@dataclass(frozen=True)
class PickRateRow:
    user_id: int
    username: str
    settled: int
    correct: int

    @property
    def rate(self) -> float:
        if self.settled <= 0:
            return 0.0
        return self.correct / self.settled


class Command(BaseCommand):
    help = (
        "Print read-only statistics for a season. "
        "Defaults to the latest finished season (by end datetime)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--season-id",
            type=int,
            default=None,
            help="Primary key of the Season to report on (default: latest finished season).",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=10,
            help="How many rows to show in each ranked section (default: 10).",
        )
        parser.add_argument(
            "--min-settled",
            type=int,
            default=5,
            help=(
                "Minimum settled picks (events with a non-forfeited outcome) "
                "to include a user in pick-rate rankings (default: 5)."
            ),
        )

    def handle(self, *args, **options) -> None:
        season_id = options["season_id"]
        top_n: int = options["top"]
        min_settled: int = options["min_settled"]

        if season_id is not None:
            try:
                season = Season.objects.get(pk=season_id)
            except Season.DoesNotExist as exc:
                raise CommandError(f"Season with id={season_id} does not exist.") from exc
        else:
            season = resolve_latest_finished_season()
            if season is None:
                raise CommandError(
                    "No finished season found (end datetime before now). "
                    "Create a past season or pass --season-id explicitly."
                )

        start = season.start_datetime
        end = season.end_datetime

        self.stdout.write(self.style.NOTICE("=== Season overview ==="))
        self.stdout.write(f"Season id: {season.pk}")
        self.stdout.write(f"Name: {season.name}")
        self.stdout.write(f"Start: {start}")
        self.stdout.write(f"End: {end}")
        self.stdout.write("")

        season_events = PredictionEvent.objects.filter(
            deadline__gte=start,
            deadline__lte=end,
        )
        event_count = season_events.count()

        outcomes_qs = EventOutcome.objects.filter(prediction_event__in=season_events).select_related(
            "winning_option",
            "winning_option__option",
            "winning_generic_option",
        )
        outcomes_by_event: dict[int, EventOutcome] = {}
        forfeited_event_ids: set[int] = set()
        for outcome in outcomes_qs:
            eid = outcome.prediction_event_id
            outcomes_by_event[eid] = outcome
            if _is_forfeited_match(outcome):
                forfeited_event_ids.add(eid)

        tips_qs = UserTip.objects.filter(
            prediction_event__deadline__gte=start,
            prediction_event__deadline__lte=end,
        )

        self.stdout.write(self.style.NOTICE("=== Volume ==="))
        self.stdout.write(f"Season participants (enrolled): {SeasonParticipant.objects.filter(season=season).count()}")
        self.stdout.write(f"Prediction events (by deadline in window): {event_count}")
        self.stdout.write(f"Event outcomes recorded: {len(outcomes_by_event)}")
        self.stdout.write(f"Forfeited outcomes (excluded from pick rate): {len(forfeited_event_ids)}")
        self.stdout.write(f"User tips (by event deadline in window): {tips_qs.count()}")
        self.stdout.write("")

        self._print_top_tip_volume(tips_qs, top_n)
        self._print_top_points(start, end, top_n)

        settled_by_user, correct_by_user = self._compute_pick_counts(
            tips_qs, outcomes_by_event, forfeited_event_ids
        )
        self._print_pick_rates(settled_by_user, correct_by_user, min_settled, top_n)
        self._print_global_pick_rate(settled_by_user, correct_by_user)

        self._print_lock_breakdown(tips_qs)
        self._print_achievements(season)
        self._print_hotness(season, top_n)
        self._print_kudos(season, top_n)

    def _print_top_tip_volume(self, tips_qs, top_n: int) -> None:
        self.stdout.write(self.style.NOTICE("=== Most tips (by event deadline in season) ==="))
        rows = (
            tips_qs.values("user_id")
            .annotate(n=Count("id"))
            .order_by("-n")[: max(1, top_n)]
        )
        user_ids = [r["user_id"] for r in rows]
        names = {u.id: u.get_username() for u in User.objects.filter(id__in=user_ids)}
        for r in rows:
            uid = r["user_id"]
            self.stdout.write(f"  {names.get(uid, uid)}: {r['n']}")
        self.stdout.write("")

    def _print_top_points(self, start, end, top_n: int) -> None:
        self.stdout.write(self.style.NOTICE("=== Most points (UserEventScore.awarded_at in season) ==="))
        rows = (
            UserEventScore.objects.filter(awarded_at__gte=start, awarded_at__lte=end)
            .values("user_id")
            .annotate(pts=Sum("points_awarded"))
            .order_by("-pts")[: max(1, top_n)]
        )
        user_ids = [r["user_id"] for r in rows]
        names = {u.id: u.get_username() for u in User.objects.filter(id__in=user_ids)}
        for r in rows:
            uid = r["user_id"]
            self.stdout.write(f"  {names.get(uid, uid)}: {r['pts']}")
        if not rows:
            self.stdout.write("  (no scores in this window)")
        self.stdout.write("")

    def _compute_pick_counts(
        self,
        tips_qs,
        outcomes_by_event: dict[int, EventOutcome],
        forfeited_event_ids: set[int],
    ) -> tuple[dict[int, int], dict[int, int]]:
        settled_by_user: dict[int, int] = defaultdict(int)
        correct_by_user: dict[int, int] = defaultdict(int)

        tips_iter: Iterable[UserTip] = tips_qs.select_related(
            "prediction_option",
            "selected_option",
            "prediction_option__option",
        ).iterator(chunk_size=2000)

        for tip in tips_iter:
            outcome = outcomes_by_event.get(tip.prediction_event_id)
            if outcome is None:
                continue
            if tip.prediction_event_id in forfeited_event_ids:
                continue
            settled_by_user[tip.user_id] += 1
            if _tip_matches_outcome(tip, outcome):
                correct_by_user[tip.user_id] += 1

        return settled_by_user, correct_by_user

    def _print_pick_rates(
        self,
        settled_by_user: dict[int, int],
        correct_by_user: dict[int, int],
        min_settled: int,
        top_n: int,
    ) -> None:
        self.stdout.write(
            self.style.NOTICE(
                f"=== Pick rate (settled = tip on event with non-forfeited outcome; "
                f"min {min_settled} settled for rankings) ==="
            )
        )
        rows: list[PickRateRow] = []
        eligible_ids = [uid for uid, s in settled_by_user.items() if s >= min_settled]
        id_to_name = dict(User.objects.filter(id__in=eligible_ids).values_list("id", "username"))
        for uid in eligible_ids:
            settled = settled_by_user[uid]
            correct = correct_by_user.get(uid, 0)
            username = id_to_name.get(uid) or str(uid)
            rows.append(PickRateRow(user_id=uid, username=username, settled=settled, correct=correct))

        rows_best = sorted(rows, key=lambda r: (r.rate, r.settled), reverse=True)[: max(1, top_n)]
        self.stdout.write("Highest rate:")
        for r in rows_best:
            self.stdout.write(
                f"  {r.username}: {r.correct}/{r.settled} ({r.rate:.1%})"
            )
        if not rows_best:
            self.stdout.write("  (no users meet the threshold)")

        eligible_low = [r for r in rows if r.correct < r.settled]
        rows_worst = sorted(eligible_low, key=lambda r: (r.rate, -r.settled))[: max(1, top_n)]
        self.stdout.write("Lowest rate (among users with at least one wrong pick):")
        for r in rows_worst:
            self.stdout.write(
                f"  {r.username}: {r.correct}/{r.settled} ({r.rate:.1%})"
            )
        if not rows_worst:
            self.stdout.write("  (none)")
        self.stdout.write("")

    def _print_global_pick_rate(
        self, settled_by_user: dict[int, int], correct_by_user: dict[int, int]
    ) -> None:
        total_settled = sum(settled_by_user.values())
        total_correct = sum(correct_by_user.get(uid, 0) for uid in settled_by_user)
        self.stdout.write(self.style.NOTICE("=== All users combined (settled picks) ==="))
        if total_settled:
            self.stdout.write(
                f"  {total_correct}/{total_settled} ({total_correct / total_settled:.1%})"
            )
        else:
            self.stdout.write("  (no settled picks)")
        self.stdout.write("")

    def _print_lock_breakdown(self, tips_qs) -> None:
        self.stdout.write(self.style.NOTICE("=== Lock status (tips in season) ==="))
        rows = tips_qs.values("lock_status").annotate(n=Count("id")).order_by("-n")
        for r in rows:
            self.stdout.write(f"  {r['lock_status']}: {r['n']}")
        self.stdout.write("")

    def _print_achievements(self, season: Season) -> None:
        self.stdout.write(self.style.NOTICE("=== Achievements recorded for this season ==="))
        rows = (
            Achievement.objects.filter(season=season)
            .values("achievement_type")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
        if not rows:
            self.stdout.write("  (none)")
        for r in rows:
            self.stdout.write(f"  {r['achievement_type']}: {r['n']}")
        self.stdout.write("")

    def _print_hotness(self, season: Season, top_n: int) -> None:
        self.stdout.write(self.style.NOTICE("=== User hotness (season-scoped rows) ==="))
        rows = list(
            UserHotness.objects.filter(season=season)
            .select_related("user")
            .order_by("-score")[: max(1, top_n)]
        )
        if not rows:
            self.stdout.write("  (none)")
        for h in rows:
            self.stdout.write(f"  {h.user.get_username()}: {h.score:.2f}")
        self.stdout.write("")

    def _print_kudos(self, season: Season, top_n: int) -> None:
        self.stdout.write(self.style.NOTICE("=== Kudos received (season-scoped) ==="))
        kudos_rows = (
            HotnessKudos.objects.filter(season=season)
            .values("to_user_id")
            .annotate(n=Count("id"))
            .order_by("-n")[: max(1, top_n)]
        )
        user_ids = [r["to_user_id"] for r in kudos_rows]
        names = {u.id: u.get_username() for u in User.objects.filter(id__in=user_ids)}
        if not kudos_rows:
            self.stdout.write("  (none)")
        for r in kudos_rows:
            uid = r["to_user_id"]
            self.stdout.write(f"  {names.get(uid, uid)}: {r['n']}")
        self.stdout.write("")
