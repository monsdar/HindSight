from django.conf import settings
from django.db import models


class TipType(models.Model):
    class TipCategory(models.TextChoices):
        GAME = 'game', 'Spiel'
        PLAYER = 'player', 'Spieler'
        TEAM = 'team', 'Team'
        SEASON = 'season', 'Saison'

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=20,
        choices=TipCategory.choices,
        default=TipCategory.GAME,
    )
    deadline = models.DateTimeField(
        help_text='Nach Ablauf dieser Zeit sind keine Tipps mehr möglich.'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['deadline']
        verbose_name = 'Tipp-Art'
        verbose_name_plural = 'Tipp-Arten'

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

    class Meta:
        ordering = ['game_date']
        verbose_name = 'Anstehendes Spiel'
        verbose_name_plural = 'Anstehende Spiele'

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
        verbose_name = 'Tipp'
        verbose_name_plural = 'Tipps'

    def __str__(self) -> str:
        if self.scheduled_game:
            return f"{self.user} - {self.scheduled_game}: {self.prediction}"
        return f"{self.user} - {self.tip_type}: {self.prediction}"
