"""
DBB event source using the SLAPI API.

This source provides German basketball teams and match predictions.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from django.utils import timezone

from hooptipp.predictions.event_sources.base import EventSource, EventSourceResult
from hooptipp.predictions.models import (
    Option,
    OptionCategory,
    PredictionEvent,
    PredictionOption,
    TipType,
)

from .client import build_slapi_client
from .logo_matcher import discover_logo_files, find_logo_for_team, get_logo_for_team
from .models import DbbMatch, TrackedLeague, TrackedTeam

logger = logging.getLogger(__name__)


class DbbEventSource(EventSource):
    """Event source for German basketball matches via SLAPI API."""

    @property
    def source_id(self) -> str:
        return "dbb-slapi"

    @property
    def source_name(self) -> str:
        return "German Basketball (SLAPI)"

    @property
    def category_slugs(self) -> list[str]:
        return ["dbb-teams"]

    def is_configured(self) -> bool:
        """Check if SLAPI API token is configured."""
        client = build_slapi_client()
        return client is not None

    def get_configuration_help(self) -> str:
        if self.is_configured():
            return "DBB source is configured and ready to use."
        return (
            "To configure the DBB source, set the SLAPI_API_TOKEN "
            "environment variable with your SLAPI API key."
        )

    def sync_options(self) -> EventSourceResult:
        """
        Sync team options from tracked teams.
        
        Creates/updates Options for all tracked teams.
        """
        result = EventSourceResult()

        if not self.is_configured():
            result.add_error("DBB source is not configured (missing API token)")
            return result

        try:
            # Discover available logos once for all teams
            logo_map = discover_logo_files()
            
            # Ensure category exists
            category, _ = OptionCategory.objects.get_or_create(
                slug='dbb-teams',
                defaults={
                    'name': 'German Basketball Teams',
                    'description': 'Teams from German amateur basketball leagues',
                    'icon': 'basketball',
                    'is_active': True,
                }
            )

            # Get all active tracked teams
            tracked_teams = TrackedTeam.objects.filter(is_active=True).select_related('tracked_league')

            for team in tracked_teams:
                # Create or update option for this team
                metadata = {
                    'league_name': team.tracked_league.league_name,
                    'league_id': team.tracked_league.league_id,
                    'verband_name': team.tracked_league.verband_name,
                }
                
                # Get logo (manual assignment takes precedence over auto-discovery)
                logo = get_logo_for_team(team.team_name, team.logo)
                if logo:
                    metadata['logo'] = logo
                
                option, created = Option.objects.update_or_create(
                    category=category,
                    slug=self._slugify_team_name(team.team_name),
                    defaults={
                        'name': team.team_name,
                        'short_name': self._extract_short_name(team.team_name),
                        'external_id': team.team_id or '',
                        'metadata': metadata,
                        'is_active': True,
                    }
                )

                if created:
                    result.options_created += 1
                else:
                    result.options_updated += 1

        except Exception as e:
            logger.exception(f"Error syncing DBB options: {e}")
            result.add_error(f"Failed to sync DBB options: {str(e)}")

        return result

    def sync_events(self, limit: int = 7) -> EventSourceResult:
        """
        Sync DBB matches as prediction events.
        
        Fetches matches for all tracked leagues and creates prediction events.
        """
        result = EventSourceResult()

        if not self.is_configured():
            result.add_error("DBB source is not configured (missing API token)")
            return result

        try:
            # Discover available logos once for all teams
            logo_map = discover_logo_files()
            
            client = build_slapi_client()
            if not client:
                result.add_error("Failed to build SLAPI client")
                return result

            # Get or create tip type for DBB matches
            tip_type, _ = TipType.objects.get_or_create(
                slug='dbb-matches',
                defaults={
                    'name': 'German Basketball Matches',
                    'description': 'German amateur basketball league matches',
                    'category': TipType.TipCategory.GAME,
                    'deadline': timezone.now(),
                    'is_active': True,
                    'default_points': 1,
                }
            )

            # Get all active tracked leagues
            tracked_leagues = TrackedLeague.objects.filter(is_active=True).prefetch_related('teams')

            for league in tracked_leagues:
                try:
                    # Fetch matches for this league
                    matches = client.get_league_matches(league.league_id)
                    
                    # Get tracked team names for filtering
                    tracked_team_names = set(
                        team.team_name for team in league.teams.filter(is_active=True)
                    )

                    for match_data in matches:
                        # Extract match information
                        # Note: home_team and away_team are objects with structure {"id": "...", "name": "...", ...}
                        home_team_obj = match_data.get('home_team', {})
                        away_team_obj = match_data.get('away_team', {})
                        
                        if isinstance(home_team_obj, dict):
                            home_team = home_team_obj.get('name', '')
                        else:
                            home_team = match_data.get('home_team', '')  # Fallback
                        
                        if isinstance(away_team_obj, dict):
                            away_team = away_team_obj.get('name', '')
                        else:
                            away_team = match_data.get('away_team', '')  # Fallback
                        
                        # Check if this match involves any of our tracked teams
                        if home_team not in tracked_team_names and away_team not in tracked_team_names:
                            continue

                        match_id = str(match_data.get('match_id', ''))
                        if not match_id:
                            continue

                        # Parse match date
                        match_date_str = match_data.get('date', '') or match_data.get('datetime', '')
                        if not match_date_str:
                            continue

                        try:
                            match_date = self._parse_datetime(match_date_str)
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Failed to parse date '{match_date_str}': {e}")
                            continue

                        # Skip past matches
                        if match_date < timezone.now():
                            continue

                        # Create or update DbbMatch
                        dbb_match, match_created = DbbMatch.objects.update_or_create(
                            external_match_id=match_id,
                            defaults={
                                'tip_type': tip_type,
                                'match_date': match_date,
                                'home_team': home_team,
                                'away_team': away_team,
                                'venue': match_data.get('venue') or match_data.get('location') or None,
                                'league_name': league.league_name,
                                'tracked_league': league,
                                'metadata': match_data,
                            }
                        )

                        # Check if prediction event already exists
                        existing_event = PredictionEvent.objects.filter(
                            source_id=self.source_id,
                            source_event_id=match_id
                        ).first()

                        if existing_event:
                            # Update existing event
                            existing_event.deadline = match_date
                            existing_event.name = f"{away_team} @ {home_team}"
                            existing_event.save()
                            event = existing_event
                            result.events_updated += 1
                        else:
                            # Create new prediction event
                            event = PredictionEvent.objects.create(
                                tip_type=tip_type,
                                name=f"{away_team} @ {home_team}",
                                description=f"{away_team} at {home_team} ({league.league_name})",
                                target_kind=PredictionEvent.TargetKind.TEAM,
                                selection_mode=PredictionEvent.SelectionMode.CURATED,
                                source_id=self.source_id,
                                source_event_id=match_id,
                                metadata={
                                    'league_name': league.league_name,
                                    'league_id': league.league_id,
                                    'verband_name': league.verband_name,
                                    'venue': dbb_match.venue,
                                },
                                opens_at=timezone.now(),
                                deadline=match_date,
                                reveal_at=timezone.now(),
                                is_active=True,
                                points=tip_type.default_points,
                            )
                            result.events_created += 1

                        # Create/ensure prediction options for teams (for both new and updated events)
                        category = OptionCategory.objects.get(slug='dbb-teams')
                        
                        # Get or create away team option
                        away_option = Option.objects.filter(
                            category=category,
                            name=away_team
                        ).first()
                        
                        # Update logo if option exists but doesn't have one
                        if away_option and not away_option.metadata.get('logo'):
                            away_logo = find_logo_for_team(away_team, logo_map)
                            if away_logo:
                                away_option.metadata['logo'] = away_logo
                                away_option.save(update_fields=['metadata'])
                        
                        if not away_option:
                            # Create option for opponent team even if not tracked
                            away_slug = self._slugify_team_name(away_team)
                            away_short_name = self._extract_short_name(away_team)
                            # Auto-discover logo for opponent team
                            away_logo = find_logo_for_team(away_team, logo_map)
                            away_metadata = {}
                            if away_logo:
                                away_metadata['logo'] = away_logo
                            away_option = Option.objects.create(
                                category=category,
                                slug=away_slug,
                                name=away_team,
                                short_name=away_short_name,
                                metadata=away_metadata,
                            )
                        
                        # Get or create home team option
                        home_option = Option.objects.filter(
                            category=category,
                            name=home_team
                        ).first()
                        
                        # Update logo if option exists but doesn't have one
                        if home_option and not home_option.metadata.get('logo'):
                            home_logo = find_logo_for_team(home_team, logo_map)
                            if home_logo:
                                home_option.metadata['logo'] = home_logo
                                home_option.save(update_fields=['metadata'])
                        
                        if not home_option:
                            # Create option for opponent team even if not tracked
                            home_slug = self._slugify_team_name(home_team)
                            home_short_name = self._extract_short_name(home_team)
                            # Auto-discover logo for opponent team
                            home_logo = find_logo_for_team(home_team, logo_map)
                            home_metadata = {}
                            if home_logo:
                                home_metadata['logo'] = home_logo
                            home_option = Option.objects.create(
                                category=category,
                                slug=home_slug,
                                name=home_team,
                                short_name=home_short_name,
                                metadata=home_metadata,
                            )

                        # Create prediction options if they don't exist
                        if not event.options.filter(option=away_option).exists():
                            PredictionOption.objects.create(
                                event=event,
                                option=away_option,
                                label=away_option.name,
                                sort_order=1,
                                is_active=True,
                            )

                        if not event.options.filter(option=home_option).exists():
                            PredictionOption.objects.create(
                                event=event,
                                option=home_option,
                                label=home_option.name,
                                sort_order=2,
                                is_active=True,
                            )

                except Exception as e:
                    logger.exception(f"Error syncing matches for league {league.league_name}: {e}")
                    result.add_error(f"Failed to sync league {league.league_name}: {str(e)}")

        except Exception as e:
            logger.exception(f"Error syncing DBB events: {e}")
            result.add_error(f"Failed to sync DBB events: {str(e)}")

        return result

    def _slugify_team_name(self, team_name: str) -> str:
        """Create a slug from team name."""
        from django.utils.text import slugify
        return slugify(team_name)

    def _extract_short_name(self, team_name: str) -> str:
        """Extract a short name from the full team name."""
        # Try to extract an abbreviation or use first 20 chars
        parts = team_name.split()
        if len(parts) >= 2:
            # Take first letters of first two words
            return ''.join(word[0].upper() for word in parts[:2] if word)
        return team_name[:20]

    def _parse_datetime(self, date_str: str) -> datetime:
        """Parse a datetime string from SLAPI API."""
        # Try ISO format first
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            return dt
        except (ValueError, AttributeError):
            pass

        # Try other common formats
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%d.%m.%Y %H:%M',
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt)
                return dt
            except ValueError:
                continue

        raise ValueError(f"Unable to parse datetime: {date_str}")

