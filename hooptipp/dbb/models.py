"""DBB-specific models."""

from __future__ import annotations

from django.db import models


class TrackedLeague(models.Model):
    """
    Stores leagues that the admin has selected to follow.
    
    A league represents a competition within a Verband that the club participates in.
    """
    verband_name = models.CharField(max_length=200, help_text="Name of the Verband")
    verband_id = models.CharField(max_length=100, help_text="External ID from SLAPI")
    league_name = models.CharField(max_length=200, help_text="Name of the league")
    league_id = models.CharField(max_length=100, help_text="External ID from SLAPI")
    club_search_term = models.CharField(
        max_length=200,
        help_text="The search term used to find the club (e.g., 'Bierden-Bassen')"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether to actively track matches for this league"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['verband_name', 'league_name']
        verbose_name = 'Tracked league'
        verbose_name_plural = 'Tracked leagues'
        unique_together = ('verband_id', 'league_id')
        app_label = 'dbb'

    def __str__(self) -> str:
        return f"{self.league_name} ({self.verband_name})"


class TrackedTeam(models.Model):
    """
    Stores specific teams to track within a league.
    
    Multiple teams from the same club can exist in the same league.
    """
    tracked_league = models.ForeignKey(
        TrackedLeague,
        on_delete=models.CASCADE,
        related_name='teams'
    )
    team_name = models.CharField(max_length=200, help_text="Full team name from API")
    team_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="External ID from SLAPI (if available)"
    )
    logo = models.CharField(
        max_length=200,
        blank=True,
        help_text="Logo filename (optional - will auto-discover from static/dbb/ if blank)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether to track matches for this team"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['team_name']
        verbose_name = 'Tracked team'
        verbose_name_plural = 'Tracked teams'
        unique_together = ('tracked_league', 'team_name')
        app_label = 'dbb'

    def __str__(self) -> str:
        return f"{self.team_name} ({self.tracked_league.league_name})"


class DbbMatch(models.Model):
    """
    Stores individual German basketball matches.
    
    Similar to ScheduledGame in the NBA module.
    """
    tip_type = models.ForeignKey(
        'predictions.TipType',
        on_delete=models.CASCADE,
        related_name='dbb_matches'
    )
    external_match_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique match ID from SLAPI"
    )
    match_date = models.DateTimeField(help_text="Match start time")
    home_team = models.CharField(max_length=200, help_text="Home team name")
    away_team = models.CharField(max_length=200, help_text="Away team name")
    venue = models.CharField(max_length=200, blank=True, null=True, help_text="Venue/location")
    league_name = models.CharField(
        max_length=200,
        help_text="League name for context"
    )
    tracked_league = models.ForeignKey(
        TrackedLeague,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='matches',
        help_text="Reference to the tracked league"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional match data from SLAPI"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['match_date']
        verbose_name = 'DBB match'
        verbose_name_plural = 'DBB matches'
        app_label = 'dbb'

    def __str__(self) -> str:
        return f"{self.away_team} @ {self.home_team}"

