"""NBA-specific models."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class ScheduledGame(models.Model):
    """NBA game scheduling model."""

    tip_type = models.ForeignKey(
        'predictions.TipType',
        on_delete=models.CASCADE,
        related_name='nba_games',
    )
    nba_game_id = models.CharField(max_length=20, unique=True)
    game_date = models.DateTimeField()

    # Team references via Options
    home_team_option = models.ForeignKey(
        'predictions.Option',
        on_delete=models.CASCADE,
        related_name='nba_home_games',
        null=True,
        blank=True,
    )
    away_team_option = models.ForeignKey(
        'predictions.Option',
        on_delete=models.CASCADE,
        related_name='nba_away_games',
        null=True,
        blank=True,
    )

    # Denormalized fields for convenience
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
        verbose_name = 'NBA scheduled game'
        verbose_name_plural = 'NBA scheduled games'

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


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_nba_preferences(sender, instance, created, **kwargs):
    """Auto-create NBA preferences when a user is created."""
    if created:
        NbaUserPreferences.objects.get_or_create(user=instance)
