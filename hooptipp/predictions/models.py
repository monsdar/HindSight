from __future__ import annotations

from datetime import date, time, datetime
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from django.dispatch import receiver
from PIL import Image
import os

from .theme_palettes import DEFAULT_THEME_KEY, THEME_CHOICES, get_theme_palette


def validate_square_image(image):
    """Validate that the uploaded image is square (1:1 ratio)."""
    try:
        with Image.open(image) as img:
            width, height = img.size
            if width != height:
                raise ValidationError(
                    f"Image must be square (1:1 ratio). Current dimensions: {width}x{height}. "
                    f"Please crop your image to be square before uploading."
                )
    except Exception as e:
        raise ValidationError(f"Invalid image file: {str(e)}")


def process_profile_picture(instance, filename):
    """Process and resize profile picture to 256x256 pixels."""
    # Validate the image is square first
    validate_square_image(instance.profile_picture.file)
    
    try:
        with Image.open(instance.profile_picture.file) as img:
            # Convert to RGB if necessary (handles RGBA, P mode images)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Resize to 256x256
            img = img.resize((256, 256), Image.Resampling.LANCZOS)
            
            # Save to a new file
            output = ContentFile(b'')
            img.save(output, format='JPEG', quality=95, optimize=True)
            output.seek(0)
            
            # Update the file content
            instance.profile_picture.save(
                filename,
                ContentFile(output.read()),
                save=False
            )
    except Exception as e:
        raise ValidationError(f"Failed to process image: {str(e)}")


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
        WAS_LOCKED = "was_locked", "Was locked"
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
    lock_forfeited_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the lock was forfeited (used for season-aware restoration).",
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
    profile_picture = models.ImageField(
        upload_to='profile_pictures/',
        blank=True,
        null=True,
        help_text="User profile picture (must be square, will be resized to 256x256px)",
        validators=[validate_square_image]
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


class Season(models.Model):
    """
    Represents a time-bounded scoring period.
    
    Only one season can be active at a time (determined by current datetime
    falling within start_datetime and end_datetime). When a season is active,
    leaderboards show only scores from that season's timeframe.
    """
    name = models.CharField(max_length=200)
    start_date = models.DateField(
        help_text="Date when the season starts"
    )
    start_time = models.TimeField(
        default=time(0, 0, 0),
        help_text="Time when the season starts (defaults to 00:00:00)"
    )
    end_date = models.DateField(
        help_text="Date when the season ends"
    )
    end_time = models.TimeField(
        default=time(23, 59, 59),
        help_text="Time when the season ends (defaults to 23:59:59)"
    )
    description = models.TextField(blank=True)
    season_end_description = models.TextField(
        blank=True,
        help_text="Description to display when the season has ended (replaces normal description)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', '-start_time', 'name']
        verbose_name = 'Season'
        verbose_name_plural = 'Seasons'
        indexes = [
            models.Index(fields=['start_date', 'start_time', 'end_date', 'end_time']),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def start_datetime(self) -> timezone.datetime:
        """Get the combined start date and time as a timezone-aware datetime."""
        if self.start_date is None:
            raise ValueError(
                f"Season '{self.name}' (id={self.pk}) has no start_date set. "
                "This is a required field. Please set it in the admin interface."
            )
        time_val = self.start_time if self.start_time is not None else time(0, 0, 0)
        dt = datetime.combine(self.start_date, time_val)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt

    @property
    def end_datetime(self) -> timezone.datetime:
        """Get the combined end date and time as a timezone-aware datetime."""
        if self.end_date is None:
            raise ValueError(
                f"Season '{self.name}' (id={self.pk}) has no end_date set. "
                "This is a required field. Please set it in the admin interface."
            )
        time_val = self.end_time if self.end_time is not None else time(23, 59, 59)
        dt = datetime.combine(self.end_date, time_val)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt

    def clean(self) -> None:
        """Validate that end_datetime >= start_datetime and no overlapping seasons."""
        start_dt = self.start_datetime
        end_dt = self.end_datetime
        
        if end_dt < start_dt:
            raise ValidationError({
                'end_date': 'End date/time must be on or after start date/time.'
            })
        
        # Check for overlapping seasons (excluding self if updating)
        # We need to check all seasons and compare their datetime ranges
        overlapping = Season.objects.exclude(pk=self.pk) if self.pk else Season.objects.all()
        
        for other_season in overlapping:
            other_start = other_season.start_datetime
            other_end = other_season.end_datetime
            
            # Check if ranges overlap: (start <= other_end) and (end >= other_start)
            if start_dt <= other_end and end_dt >= other_start:
                raise ValidationError(
                    f'This season overlaps with existing season "{other_season.name}". '
                    f'Seasons must have non-overlapping timeframes.'
                )

    def save(self, *args, **kwargs) -> None:
        """Override save to call clean() for validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    def is_active(self, check_datetime: timezone.datetime | None = None) -> bool:
        """Check if this season is active at the given datetime (or now if not provided)."""
        # Skip seasons with missing required fields
        if self.start_date is None or self.end_date is None:
            return False
        if check_datetime is None:
            check_datetime = timezone.now()
        # Ensure check_datetime is timezone-aware
        if timezone.is_naive(check_datetime):
            check_datetime = timezone.make_aware(check_datetime)
        return self.start_datetime <= check_datetime <= self.end_datetime

    @classmethod
    def get_active_season(cls, check_datetime: timezone.datetime | None = None) -> 'Season | None':
        """Get the currently active season, if any."""
        if check_datetime is None:
            check_datetime = timezone.now()
        # Ensure check_datetime is timezone-aware
        if timezone.is_naive(check_datetime):
            check_datetime = timezone.make_aware(check_datetime)
        
        # Filter out seasons with null dates and check all valid seasons
        for season in cls.objects.exclude(start_date__isnull=True).exclude(end_date__isnull=True):
            try:
                if season.is_active(check_datetime):
                    return season
            except (ValueError, AttributeError):
                # Skip seasons with invalid data
                continue
        return None


class SeasonParticipant(models.Model):
    """
    Represents a user's enrollment in a specific season.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'season')
        ordering = ['-enrolled_at']
        verbose_name = 'Season Participant'
        verbose_name_plural = 'Season Participants'

    def __str__(self) -> str:
        return f"{self.user.username} - {self.season.name}"


class Achievement(models.Model):
    """
    Represents an achievement awarded to a user.
    
    Achievements can be tied to seasons (e.g., top 3 finishers) or be
    independent (e.g., registration milestones, prediction counts).
    """
    class AchievementType(models.TextChoices):
        SEASON_GOLD = 'season_gold', 'Season Gold Medal'
        SEASON_SILVER = 'season_silver', 'Season Silver Medal'
        SEASON_BRONZE = 'season_bronze', 'Season Bronze Medal'
        BETA_TESTER = 'beta_tester', 'Beta Tester'
        # Future achievement types can be added here:
        # REGISTRATION_1YEAR = 'registration_1year', 'Registered 1 Year'
        # PREDICTIONS_100 = 'predictions_100', '100 Correct Predictions'
        # LAST_PLACE = 'last_place', 'Last Place Finisher'
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='achievements'
    )
    season = models.ForeignKey(
        'Season',
        on_delete=models.CASCADE,
        related_name='achievements',
        null=True,
        blank=True,
        help_text="Season this achievement is tied to (null for non-season achievements)"
    )
    achievement_type = models.CharField(
        max_length=50,
        choices=AchievementType.choices,
        help_text="Type of achievement"
    )
    name = models.CharField(
        max_length=200,
        help_text="Display name of the achievement (e.g., 'Season Champion')"
    )
    description = models.TextField(
        blank=True,
        help_text="Short description of the achievement"
    )
    emoji = models.CharField(
        max_length=10,
        help_text="Emoji icon for the achievement (e.g., '🥇')"
    )
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'season', 'achievement_type')
        ordering = ['-awarded_at', 'achievement_type']
        verbose_name = 'Achievement'
        verbose_name_plural = 'Achievements'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['season']),
            models.Index(fields=['achievement_type']),
        ]

    def __str__(self) -> str:
        season_str = f" - {self.season.name}" if self.season else ""
        return f"{self.user.username}: {self.name}{season_str}"


class ImpressumSection(models.Model):
    """
    Represents a section of the Impressum (legal notice).
    
    Admins can create multiple sections with captions and markdown text.
    Sections are ordered by order_number (lower numbers appear first).
    """
    caption = models.CharField(max_length=200)
    text = models.TextField(help_text="Markdown content for this section")
    order_number = models.PositiveIntegerField(
        default=0,
        help_text="Lower numbers appear first. Sections with the same order_number are ordered by caption."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order_number', 'caption']
        verbose_name = 'Impressum section'
        verbose_name_plural = 'Impressum sections'

    def __str__(self) -> str:
        return self.caption


class DatenschutzSection(models.Model):
    """
    Represents a section of the Datenschutzerklärung (privacy policy).
    
    Admins can create multiple sections with captions and markdown text.
    Sections are ordered by order_number (lower numbers appear first).
    """
    caption = models.CharField(max_length=200)
    text = models.TextField(help_text="Markdown content for this section")
    order_number = models.PositiveIntegerField(
        default=0,
        help_text="Lower numbers appear first. Sections with the same order_number are ordered by caption."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order_number', 'caption']
        verbose_name = 'Datenschutz section'
        verbose_name_plural = 'Datenschutz sections'

    def __str__(self) -> str:
        return self.caption


class TeilnahmebedingungenSection(models.Model):
    """
    Represents a section of the Teilnahmebedingungen (terms of participation).
    
    Admins can create multiple sections with captions and markdown text.
    Sections are ordered by order_number (lower numbers appear first).
    """
    caption = models.CharField(max_length=200)
    text = models.TextField(help_text="Markdown content for this section")
    order_number = models.PositiveIntegerField(
        default=0,
        help_text="Lower numbers appear first. Sections with the same order_number are ordered by caption."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order_number', 'caption']
        verbose_name = 'Teilnahmebedingungen section'
        verbose_name_plural = 'Teilnahmebedingungen sections'

    def __str__(self) -> str:
        return self.caption


class UserHotness(models.Model):
    """
    Tracks a user's current hotness score - a dynamic social + performance metric.
    Resets when new season starts. Decays over time based on HotnessSettings.decay_per_hour.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='hotness_scores'
    )
    score = models.FloatField(default=0.0)
    season = models.ForeignKey(
        'Season',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='hotness_scores',
        help_text="Season this hotness score belongs to"
    )
    last_decay = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('user', 'season')
        ordering = ['-score', 'user__username']
        verbose_name = 'User hotness'
        verbose_name_plural = 'User hotness scores'
    
    def __str__(self):
        season_str = f" ({self.season.name})" if self.season else " (All-time)"
        return f"{self.user.username}: {self.score:.1f}{season_str}"
    
    def get_level(self) -> int:
        """Returns hotness level 0-4 based on score."""
        if self.score >= 100: return 4
        if self.score >= 50: return 3
        if self.score >= 25: return 2
        if self.score >= 10: return 1
        return 0
    
    def decay(self) -> None:
        """Apply time-based decay based on HotnessSettings.decay_per_hour."""
        hotness_settings = HotnessSettings.get_settings()
        
        now = timezone.now()
        hours_elapsed = (now - self.last_decay).total_seconds() / 3600
        decay_amount = hours_elapsed * hotness_settings.decay_per_hour
        
        if decay_amount > 0:
            self.score = max(0.0, self.score - decay_amount)
            self.last_decay = now
            self.save(update_fields=['score', 'last_decay'])


class HotnessKudos(models.Model):
    """
    Tracks kudos given from one user to another.
    Limited to 1 kudos per user per target per day (enforced in service layer).
    """
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kudos_given'
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kudos_received'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    season = models.ForeignKey(
        'Season',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='kudos'
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Hotness kudos'
        verbose_name_plural = 'Hotness kudos'
        indexes = [
            models.Index(fields=['to_user', 'created_at']),
            models.Index(fields=['from_user', 'created_at']),
            models.Index(fields=['from_user', 'to_user', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.from_user.username} -> {self.to_user.username} ({self.created_at.date()})"


class HotnessSettings(models.Model):
    """
    Singleton model for configuring hotness system parameters.
    
    Only one instance should exist. Use get_settings() to get or create it.
    """
    # Points awarded for correct predictions
    correct_prediction_points = models.FloatField(
        default=10.0,
        help_text="Points awarded for a correct prediction"
    )
    # Bonus points for winning with a locked prediction
    lock_win_points = models.FloatField(
        default=20.0,
        help_text="Bonus points awarded when a locked prediction is correct"
    )
    # Bonus points for streak of correct predictions
    streak_bonus_points = models.FloatField(
        default=50.0,
        help_text="Bonus points awarded for a streak of correct predictions"
    )
    # Points awarded per kudos received
    kudos_points = models.FloatField(
        default=2.0,
        help_text="Points awarded per kudos received from another user"
    )
    # Number of consecutive correct predictions required for streak bonus
    streak_length = models.PositiveIntegerField(
        default=3,
        help_text="Number of consecutive correct predictions required for streak bonus"
    )
    # Decay rate per hour
    decay_per_hour = models.FloatField(
        default=0.5,
        help_text="Hotness points lost per hour (decay rate)"
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Hotness Settings'
        verbose_name_plural = 'Hotness Settings'
    
    def __str__(self):
        return "Hotness Settings"
    
    def save(self, *args, **kwargs):
        """Ensure only one instance exists."""
        # If this is a new instance and another already exists, update that one instead
        if not self.pk:
            existing = HotnessSettings.objects.first()
            if existing:
                # Update existing instance instead of creating new one
                for field in self._meta.fields:
                    if field.name not in ('id', 'pk', 'created_at', 'updated_at'):
                        setattr(existing, field.name, getattr(self, field.name))
                existing.save()
                return
        super().save(*args, **kwargs)
    
    @classmethod
    def get_settings(cls) -> 'HotnessSettings':
        """Get or create the singleton settings instance."""
        settings, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'correct_prediction_points': 10.0,
                'lock_win_points': 20.0,
                'streak_bonus_points': 50.0,
                'kudos_points': 2.0,
                'streak_length': 3,
                'decay_per_hour': 0.5,
            }
        )
        return settings


@receiver(post_save, sender=UserPreferences)
def process_profile_picture_signal(sender, instance, created, **kwargs):
    """Automatically process and resize profile pictures when saved."""
    if instance.profile_picture and hasattr(instance.profile_picture, 'file'):
        try:
            # Get the current file path
            current_path = instance.profile_picture.path
            
            # Open and process the image
            with Image.open(current_path) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                # Resize to 256x256
                img = img.resize((256, 256), Image.Resampling.LANCZOS)
                
                # Save the processed image back to the same file
                img.save(current_path, format='JPEG', quality=95, optimize=True)
                
        except Exception as e:
            # If processing fails, we'll let the validation error handle it
            # This prevents the signal from breaking the save process
            pass
