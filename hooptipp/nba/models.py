"""NBA-specific models."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class NbaTeam(models.Model):
    """
    NBA team model.
    
    Note: The preferred approach is to use the generic Option system with
    category='nba-teams'. This model is kept for specific NBA functionality
    that requires team-specific fields.
    """
    balldontlie_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    name = models.CharField(max_length=150)
    abbreviation = models.CharField(max_length=5, blank=True)
    city = models.CharField(max_length=100, blank=True)
    conference = models.CharField(max_length=30, blank=True)
    division = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["name"]
        app_label = 'nba'

    def __str__(self) -> str:
        return self.name


class NbaPlayer(models.Model):
    """
    NBA player model.
    
    Note: The preferred approach is to use the generic Option system with
    category='nba-players'. This model is kept for specific NBA functionality
    that requires player-specific fields.
    """
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
        app_label = 'nba'

    def __str__(self) -> str:
        return self.display_name


class ScheduledGame(models.Model):
    """
    NBA scheduled game model.
    
    This model tracks individual NBA games that are part of prediction events.
    """
    tip_type = models.ForeignKey(
        'predictions.TipType',
        on_delete=models.CASCADE,
        related_name='nba_games'
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
        app_label = 'nba'

    def __str__(self) -> str:
        return f"{self.away_team} @ {self.home_team}"


class NbaUserPreferences(models.Model):
    """
    NBA-specific user preferences.

    For Option-based favorites (team/player), use UserFavorite with:
    - favorite_type='nba-team'
    - favorite_type='nba-player'
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='nba_preferences',
    )

    # NBA-specific preferences
    notifications_enabled = models.BooleanField(
        default=True,
        help_text="Receive notifications for NBA game predictions",
    )
    favorite_conference = models.CharField(
        max_length=10,
        choices=[
            ('east', 'Eastern Conference'),
            ('west', 'Western Conference'),
        ],
        blank=True,
        help_text="Preferred NBA conference for highlights",
    )
    show_player_stats = models.BooleanField(
        default=True,
        help_text="Show detailed player statistics",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'NBA user preferences'
        verbose_name_plural = 'NBA user preferences'

    def __str__(self) -> str:
        return f"NBA preferences for {self.user}"

    def get_favorite_team(self):
        """Get user's favorite NBA team Option."""
        from hooptipp.predictions.models import UserFavorite

        try:
            return UserFavorite.objects.get(
                user=self.user, favorite_type='nba-team'
            ).option
        except UserFavorite.DoesNotExist:
            return None

    def set_favorite_team(self, team_option):
        """Set user's favorite NBA team."""
        from hooptipp.predictions.models import UserFavorite

        UserFavorite.objects.update_or_create(
            user=self.user,
            favorite_type='nba-team',
            defaults={'option': team_option},
        )

    def get_favorite_player(self):
        """Get user's favorite NBA player Option."""
        from hooptipp.predictions.models import UserFavorite

        try:
            return UserFavorite.objects.get(
                user=self.user, favorite_type='nba-player'
            ).option
        except UserFavorite.DoesNotExist:
            return None

    def set_favorite_player(self, player_option):
        """Set user's favorite NBA player."""
        from hooptipp.predictions.models import UserFavorite

        UserFavorite.objects.update_or_create(
            user=self.user,
            favorite_type='nba-player',
            defaults={'option': player_option},
        )


# Note: We don't auto-create NBA preferences via signal to avoid issues
# with test database creation. Instead, create on-demand via get_or_create
# when accessed.
