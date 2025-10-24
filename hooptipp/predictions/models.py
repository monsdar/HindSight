from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from .theme_palettes import DEFAULT_THEME_KEY, THEME_CHOICES, get_theme_palette


class OptionCategory(models.Model):
    """
    Represents a category of prediction options.
    
    Examples: 'nba-teams', 'countries', 'political-parties', 'yes-no'
    This allows the system to support any type of prediction target.
    """
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon identifier for UI display (e.g., 'basketball', 'flag', 'check')"
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Option category'
        verbose_name_plural = 'Option categories'

    def __str__(self) -> str:
        return self.name


class Option(models.Model):
    """
    Generic option that can represent any selectable choice in predictions.
    
    This replaces the need for separate NbaTeam, NbaPlayer, Country, etc. models.
    All prediction targets are stored here with category-specific metadata.
    """
    category = models.ForeignKey(
        OptionCategory,
        on_delete=models.CASCADE,
        related_name='options'
    )
    slug = models.SlugField(max_length=100)
    name = models.CharField(max_length=200)
    short_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Abbreviated name (e.g., 'LAL' for Lakers, 'USA' for United States)"
    )
    description = models.TextField(blank=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Flexible storage for category-specific data (e.g., team conference, player position)"
    )
    external_id = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reference to external API/system (e.g., BallDontLie team ID)"
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('category', 'slug')
        ordering = ['category', 'sort_order', 'name']
        verbose_name = 'Option'
        verbose_name_plural = 'Options'
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['external_id']),
        ]

    def __str__(self) -> str:
        if self.short_name:
            return f"{self.name} ({self.short_name})"
        return self.name


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


class PredictionEvent(models.Model):
    class TargetKind(models.TextChoices):
        TEAM = "team", "Team"
        PLAYER = "player", "Player"
        # Generic option for non-NBA predictions
        GENERIC = "generic", "Generic"

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
    # New generic fields for extensibility
    source_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Identifier for the EventSource that created this event (e.g., 'nba-balldontlie', 'olympics-2028')",
    )
    source_event_id = models.CharField(
        max_length=200,
        blank=True,
        help_text="External event ID from the source system",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Source-specific data and additional event properties",
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
    # Legacy NBA-specific field - kept for backward compatibility
    scheduled_game = models.OneToOneField(
        "nba.ScheduledGame",
        on_delete=models.CASCADE,
        related_name="prediction_event",
        null=True,
        blank=True,
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["deadline", "sort_order", "name"]
        indexes = [
            models.Index(fields=['source_id', 'source_event_id']),
            models.Index(fields=['is_active', 'opens_at', 'deadline']),
        ]

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
    option = models.ForeignKey(
        Option,
        on_delete=models.CASCADE,
        related_name="prediction_options",
        help_text="Generic option reference for any type of prediction target",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "label"]
        unique_together = (("event", "option"),)

    def __str__(self) -> str:
        return self.label


class UserTip(models.Model):
    class LockStatus(models.TextChoices):
        NONE = "none", "No lock"
        ACTIVE = "active", "Active"
        RETURNED = "returned", "Returned"
        FORFEITED = "forfeited", "Forfeited"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tip_type = models.ForeignKey(TipType, on_delete=models.CASCADE)
    prediction_event = models.ForeignKey(
        PredictionEvent,
        on_delete=models.CASCADE,
        related_name='tips',
    )
    prediction_option = models.ForeignKey(
        PredictionOption,
        on_delete=models.SET_NULL,
        related_name='tips',
        null=True,
        blank=True,
        help_text="The specific option the user selected (references a PredictionOption from the event)",
    )
    selected_option = models.ForeignKey(
        Option,
        on_delete=models.SET_NULL,
        related_name='tips',
        null=True,
        blank=True,
        help_text="The underlying generic option selected (denormalized for easier querying)",
    )
    prediction = models.CharField(max_length=255, help_text="Human-readable prediction text")
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
        unique_together = (('user', 'prediction_event'),)
        verbose_name = 'User tip'
        verbose_name_plural = 'User tips'
        indexes = [
            models.Index(fields=['user', 'is_locked']),
            models.Index(fields=['prediction_event', 'user']),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.prediction_event}: {self.prediction}"


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
        help_text="The PredictionOption that won (includes label and event context)",
    )
    winning_generic_option = models.ForeignKey(
        "Option",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="winning_event_outcomes",
        help_text="The underlying generic Option that won (denormalized for easier querying)",
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
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional outcome data (e.g., game scores, statistics)"
    )
    scored_at = models.DateTimeField(null=True, blank=True)
    score_error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Event outcome"
        verbose_name_plural = "Event outcomes"

    def __str__(self) -> str:
        return f"Outcome for {self.prediction_event}" if self.prediction_event else "Event outcome"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        if not (self.winning_option or self.winning_generic_option):
            raise ValidationError(
                "An event outcome must specify a winning option.",
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


class UserFavorite(models.Model):
    """
    Generic favorites system - allows users to favorite any Option.

    Examples:
    - favorite_type='nba-team', option=Lakers
    - favorite_type='nba-player', option=LeBron James  
    - favorite_type='olympic-country', option=USA
    - favorite_type='olympic-sport', option=Swimming
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorites',
    )
    favorite_type = models.CharField(
        max_length=50,
        help_text="Type of favorite (e.g., 'nba-team', 'olympic-country')",
    )
    option = models.ForeignKey(
        Option,
        on_delete=models.CASCADE,
        related_name='favorited_by',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'favorite_type')
        ordering = ['favorite_type', 'created_at']
        verbose_name = 'User favorite'
        verbose_name_plural = 'User favorites'
        indexes = [
            models.Index(fields=['user', 'favorite_type']),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.favorite_type}: {self.option}"


class UserPreferences(models.Model):
    """
    Core user preferences - only truly generic settings.
    
    Sport/domain-specific preferences should be in separate models
    in their respective apps (e.g., NbaUserPreferences in nba app).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    nickname = models.CharField(max_length=50, blank=True)
    theme = models.CharField(
        max_length=32,
        choices=THEME_CHOICES,
        default=DEFAULT_THEME_KEY,
    )
    activation_pin = models.CharField(
        max_length=50,
        blank=True,
        help_text="Comma-separated NBA team abbreviations for user activation (e.g., 'LAL,GSW,BOS')"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User preferences"
        verbose_name_plural = "User preferences"

    def __str__(self) -> str:
        return f"Preferences for {self.user}"

    def theme_palette(self) -> dict[str, str]:
        return get_theme_palette(self.theme)
    
    def get_pin_teams(self) -> list[str]:
        """Get the PIN teams as a list of team abbreviations."""
        if not self.activation_pin:
            return []
        return [team.strip().upper() for team in self.activation_pin.split(',') if team.strip()]
    
    def set_pin_teams(self, teams: list[str]) -> None:
        """Set the PIN teams from a list of team abbreviations."""
        self.activation_pin = ','.join(team.strip().upper() for team in teams if team.strip())
    
    def validate_pin(self, submitted_teams: list[str]) -> bool:
        """Validate if the submitted teams match the user's PIN."""
        pin_teams = self.get_pin_teams()
        if not pin_teams:
            return False
        return set(team.strip().upper() for team in submitted_teams) == set(pin_teams)
