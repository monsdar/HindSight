from django.conf import settings
from django.db import models


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


class UserTip(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tip_type = models.ForeignKey(TipType, on_delete=models.CASCADE)
    scheduled_game = models.ForeignKey(
        ScheduledGame,
        on_delete=models.CASCADE,
        related_name='tips',
        blank=True,
        null=True,
    )
    prediction = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'tip_type', 'scheduled_game')
        verbose_name = 'User tip'
        verbose_name_plural = 'User tips'

    def __str__(self) -> str:
        if self.scheduled_game:
            return f"{self.user} - {self.scheduled_game}: {self.prediction}"
        return f"{self.user} - {self.tip_type}: {self.prediction}"
