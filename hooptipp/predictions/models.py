from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from .theme_palettes import DEFAULT_THEME_KEY, THEME_CHOICES, get_theme_palette


class TipType(models.Model):
    class TipCategory(models.TextChoices):
        GAME = 'game', 'Game'
        PLAYER = 'player', 'Player'
        TEAM = 'team', 'Team'
        SEASON = 'season', 'Season'

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=20,
        choices=TipCategory.choices,
        default=TipCategory.GAME,
    )
    default_points = models.PositiveSmallIntegerField(
        default=1,
        help_text="Base point value awarded for correctly predicting events in this tip type.",
    )
    deadline = models.DateTimeField(
        help_text='No picks can be submitted after this deadline.'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['deadline']
        verbose_name = 'Tip category'
        verbose_name_plural = 'Tip categories'

    def __str__(self) -> str:
        return self.name


class ScheduledGame(models.Model):
    tip_type = models.ForeignKey(
        TipType,
        on_delete=models.CASCADE,
        related_name='games'
    )
    nba_game_id = models.CharField(max_length=20, unique=True)
    game_date = models.DateTimeField()
    home_team = models.CharField(max_length=100)
    home_team_tricode = models.CharField(max_length=5)
    away_team = models.CharField(max_length=100)
    away_team_tricode = models.CharField(max_length=5)
    venue = models.CharField(max_length=150, blank=True)
    is_manual = models.BooleanField(
        default=False,
        help_text='Indicates that the game was added manually rather than via the BallDontLie sync.',
    )

    class Meta:
        ordering = ['game_date']
        verbose_name = 'Scheduled game'
        verbose_name_plural = 'Scheduled games'

    def __str__(self) -> str:
        return f"{self.away_team} @ {self.home_team}"


class NbaTeam(models.Model):
    balldontlie_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    name = models.CharField(max_length=150)
    abbreviation = models.CharField(max_length=5, blank=True)
    city = models.CharField(max_length=100, blank=True)
    conference = models.CharField(max_length=30, blank=True)
    division = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class NbaPlayer(models.Model):
    balldontlie_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    display_name = models.CharField(max_length=160)
    position = models.CharField(max_length=10, blank=True)
    team = models.ForeignKey(
        NbaTeam,
        on_delete=models.SET_NULL,
        related_name="players",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name


class PredictionEvent(models.Model):
    class TargetKind(models.TextChoices):
        TEAM = "team", "Team"
        PLAYER = "player", "Player"

    class SelectionMode(models.TextChoices):
        ANY = "any", "Any selection"
        CURATED = "curated", "Curated list"

    tip_type = models.ForeignKey(
        TipType,
        on_delete=models.CASCADE,
        related_name="events",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    target_kind = models.CharField(
        max_length=10,
        choices=TargetKind.choices,
        default=TargetKind.TEAM,
    )
    selection_mode = models.CharField(
        max_length=10,
        choices=SelectionMode.choices,
        default=SelectionMode.CURATED,
    )
    points = models.PositiveSmallIntegerField(
        default=1,
        help_text="Points awarded for a correct prediction on this event.",
    )
    is_bonus_event = models.BooleanField(
        default=False,
        help_text="Indicates whether this event awards more than the default tip type points.",
    )
    opens_at = models.DateTimeField()
    deadline = models.DateTimeField()
    reveal_at = models.DateTimeField(
        help_text="The event becomes visible on or after this timestamp.",
        default=timezone.now,
    )
    is_active = models.BooleanField(default=True)
    scheduled_game = models.OneToOneField(
        "ScheduledGame",
        on_delete=models.CASCADE,
        related_name="prediction_event",
        null=True,
        blank=True,
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["deadline", "sort_order", "name"]

    def __str__(self) -> str:
        return self.name

    def is_visible(self) -> bool:
        from django.utils import timezone

        now = timezone.now()
        return self.is_active and self.reveal_at <= now


class PredictionOption(models.Model):
    event = models.ForeignKey(
        PredictionEvent,
        on_delete=models.CASCADE,
        related_name="options",
    )
    label = models.CharField(max_length=200)
    team = models.ForeignKey(
        NbaTeam,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="prediction_options",
    )
    player = models.ForeignKey(
        NbaPlayer,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="prediction_options",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "label"]
        unique_together = (
            ("event", "team"),
            ("event", "player"),
        )

    def __str__(self) -> str:
        return self.label

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        if not (self.team or self.player):
            raise ValidationError("Prediction options must reference a team or player.")
        if self.team and self.player:
            raise ValidationError("Prediction options cannot reference both a team and a player.")


class UserTip(models.Model):
    class LockStatus(models.TextChoices):
        NONE = "none", "No lock"
        ACTIVE = "active", "Active"
        RETURNED = "returned", "Returned"
        FORFEITED = "forfeited", "Forfeited"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tip_type = models.ForeignKey(TipType, on_delete=models.CASCADE)
    scheduled_game = models.ForeignKey(
        ScheduledGame,
        on_delete=models.CASCADE,
        related_name='tips',
        blank=True,
        null=True,
    )
    prediction_event = models.ForeignKey(
        PredictionEvent,
        on_delete=models.CASCADE,
        related_name='tips',
        null=True,
        blank=True,
    )
    prediction_option = models.ForeignKey(
        PredictionOption,
        on_delete=models.SET_NULL,
        related_name='tips',
        null=True,
        blank=True,
    )
    selected_team = models.ForeignKey(
        NbaTeam,
        on_delete=models.SET_NULL,
        related_name='tips',
        null=True,
        blank=True,
    )
    selected_player = models.ForeignKey(
        NbaPlayer,
        on_delete=models.SET_NULL,
        related_name='tips',
        null=True,
        blank=True,
    )
    prediction = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_locked = models.BooleanField(default=False)
    lock_status = models.CharField(
        max_length=20,
        choices=LockStatus.choices,
        default=LockStatus.NONE,
    )
    lock_committed_at = models.DateTimeField(null=True, blank=True)
    lock_released_at = models.DateTimeField(null=True, blank=True)
    lock_releases_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Scheduled timestamp for automatically returning a forfeited lock.",
    )

    class Meta:
        unique_together = (
            ('user', 'tip_type', 'scheduled_game'),
            ('user', 'prediction_event'),
        )
        verbose_name = 'User tip'
        verbose_name_plural = 'User tips'

    def __str__(self) -> str:
        if self.prediction_event:
            return f"{self.user} - {self.prediction_event}: {self.prediction}"
        if self.scheduled_game:
            return f"{self.user} - {self.scheduled_game}: {self.prediction}"
        return f"{self.user} - {self.tip_type}: {self.prediction}"


class EventOutcome(models.Model):
    prediction_event = models.OneToOneField(
        PredictionEvent,
        on_delete=models.CASCADE,
        related_name="outcome",
    )
    winning_option = models.ForeignKey(
        "PredictionOption",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="winning_outcomes",
    )
    winning_team = models.ForeignKey(
        "NbaTeam",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="winning_event_outcomes",
    )
    winning_player = models.ForeignKey(
        "NbaPlayer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="winning_event_outcomes",
    )
    resolved_at = models.DateTimeField(default=timezone.now)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_event_outcomes",
    )
    notes = models.TextField(blank=True)
    scored_at = models.DateTimeField(null=True, blank=True)
    score_error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Event outcome"
        verbose_name_plural = "Event outcomes"

    def __str__(self) -> str:
        return f"Outcome for {self.prediction_event}" if self.prediction_event else "Event outcome"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        provided = [
            value
            for value in (self.winning_option, self.winning_team, self.winning_player)
            if value is not None
        ]
        if not provided:
            raise ValidationError(
                "An event outcome must specify a winning option, team, or player.",
            )


class UserEventScore(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    prediction_event = models.ForeignKey(
        PredictionEvent,
        on_delete=models.CASCADE,
        related_name="scores",
    )
    base_points = models.PositiveSmallIntegerField()
    lock_multiplier = models.PositiveSmallIntegerField(default=1)
    points_awarded = models.PositiveIntegerField()
    is_lock_bonus = models.BooleanField(default=False)
    awarded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("user", "prediction_event")
        ordering = ["-awarded_at", "user__username"]
        verbose_name = "User event score"
        verbose_name_plural = "User event scores"

    def __str__(self) -> str:
        return f"{self.user} - {self.prediction_event}: {self.points_awarded} pts"


class UserPreferences(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    nickname = models.CharField(max_length=50, blank=True)
    favorite_team_id = models.PositiveIntegerField(blank=True, null=True)
    favorite_player_id = models.PositiveIntegerField(blank=True, null=True)
    theme = models.CharField(
        max_length=32,
        choices=THEME_CHOICES,
        default=DEFAULT_THEME_KEY,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User preferences"
        verbose_name_plural = "User preferences"

    def __str__(self) -> str:
        return f"Preferences for {self.user}"

    def favorite_team_display(self) -> str:
        if not self.favorite_team_id:
            return ""
        try:
            from .services import get_team_choices
        except Exception:  # pragma: no cover - defensive import guard
            return ""
        team_lookup = {
            int(value): label
            for value, label in get_team_choices()
            if value and value.isdigit()
        }
        return team_lookup.get(self.favorite_team_id, "")

    def favorite_player_display(self) -> str:
        if not self.favorite_player_id:
            return ""
        try:
            from .services import get_player_choices
        except Exception:  # pragma: no cover - defensive import guard
            return ""
        player_lookup = {
            int(value): label
            for value, label in get_player_choices()
            if value and value.isdigit()
        }
        return player_lookup.get(self.favorite_player_id, "")

    def theme_palette(self) -> dict[str, str]:
        return get_theme_palette(self.theme)
