"""NBA-specific models."""

from __future__ import annotations

from django.conf import settings
from django.db import models

# Note: ScheduledGame is currently in predictions.models for backward compatibility
# It will be migrated to this app in a future update
# from hooptipp.predictions.models import ScheduledGame


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
