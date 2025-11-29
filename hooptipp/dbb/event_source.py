"""
DBB event source using the SLAPI API.

This source provides German basketball teams and match predictions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from hooptipp.predictions.event_sources.base import EventSource, EventSourceResult
from hooptipp.predictions.models import (
    EventOutcome,
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
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

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
                    'name': 'DBB Spiele',
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
                    logger.info(f"Fetching matches for league {league.league_name}...")
                    matches = client.get_league_matches(league.league_id)
                    logger.info(f"Found {len(matches)} matches for league {league.league_name}")
                    
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

                        # Track if this is a past match (for outcome creation)
                        is_past_match = match_date < timezone.now()

                        # Check if match is cancelled
                        is_cancelled = match_data.get('is_cancelled', False)
                        
                        # If match is cancelled, deactivate existing event (if any) and skip
                        if is_cancelled:
                            existing_event = PredictionEvent.objects.filter(
                                source_id=self.source_id,
                                source_event_id=match_id
                            ).first()
                            
                            if existing_event and existing_event.is_active:
                                existing_event.is_active = False
                                existing_event.save(update_fields=['is_active'])
                                logger.info(f"Deactivated cancelled match event: {match_id}")
                            
                            continue

                        # Fetch location data from /match/{match_id} endpoint if not available
                        # The /leagues/{league_id}/matches endpoint no longer includes location
                        location = match_data.get('location') or match_data.get('venue')
                        if not location:
                            try:
                                detailed_match = client.get_match_details(match_id)
                                location = detailed_match.get('location')
                                if location:
                                    # Update match_data with location for consistency
                                    match_data['location'] = location
                                    logger.debug(f"Fetched location for match {match_id}: {location}")
                            except Exception as e:
                                logger.warning(f"Failed to fetch location for match {match_id}: {e}")
                                # Continue without location - it's not critical

                        # Create or update DbbMatch
                        dbb_match, match_created = DbbMatch.objects.update_or_create(
                            external_match_id=match_id,
                            defaults={
                                'tip_type': tip_type,
                                'match_date': match_date,
                                'home_team': home_team,
                                'away_team': away_team,
                                'venue': location,
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
                            existing_event.name = f"{home_team} vs. {away_team}"
                            # Update metadata including venue
                            metadata = existing_event.metadata or {}
                            metadata.update({
                                'league_name': league.league_name,
                                'league_id': league.league_id,
                                'verband_name': league.verband_name,
                                'venue': dbb_match.venue,
                            })
                            existing_event.metadata = metadata
                            existing_event.save()
                            event = existing_event
                            result.events_updated += 1
                        else:
                            # Create new prediction event
                            event = PredictionEvent.objects.create(
                                tip_type=tip_type,
                                name=f"{home_team} vs. {away_team}",
                                description=f"{home_team} vs. {away_team} ({league.league_name})",
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

                        # For past matches, check if we need to create an outcome or fix swapped scores
                        if is_past_match:
                            self._create_or_fix_outcome_for_past_match(
                                event, match_id, match_data, client, home_team, away_team, result
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

    def _extract_scores(self, match_data: dict) -> tuple[Optional[int], Optional[int]]:
        """
        Extract home_score and away_score from match data.
        
        Prioritizes explicit score_home and score_away fields from the API,
        with fallback to parsing the score string.
        
        According to SLAPI API spec, matches now include:
        - score_home: integer (nullable) - explicit home team score
        - score_away: integer (nullable) - explicit away team score
        - score: string (nullable) - score string for backwards compatibility
        
        Args:
            match_data: Match data dictionary from SLAPI
            
        Returns:
            Tuple of (home_score, away_score) or (None, None) if scores unavailable
        """
        # First, try to use explicit score fields (preferred method)
        score_home = match_data.get('score_home')
        score_away = match_data.get('score_away')
        
        if score_home is not None and score_away is not None:
            try:
                return int(score_home), int(score_away)
            except (ValueError, TypeError):
                logger.warning(f"Invalid score_home or score_away values: {score_home}, {score_away}")
        
        # Fallback to parsing score string (for backwards compatibility)
        score_str = match_data.get('score')
        if score_str:
            return self._parse_score_string(score_str)
        
        return None, None
    
    def _parse_score_string(self, score_str: str) -> tuple[Optional[int], Optional[int]]:
        """
        Parse a score string from SLAPI into home_score and away_score.
        
        The score field from SLAPI is in European order (home:away), so formats like:
        - "85:78" (home:away, meaning home=85, away=78)
        - "78 - 85" (home - away)
        - "85-78" (home-away)
        
        Args:
            score_str: The score string from the API
            
        Returns:
            Tuple of (home_score, away_score) or (None, None) if parsing fails
        """
        if not score_str:
            return None, None
        
        # Try common separators: colon, dash, hyphen
        for separator in [':', ' - ', '-', '–', '—']:
            if separator in score_str:
                parts = score_str.split(separator, 1)
                if len(parts) == 2:
                    try:
                        # European order: first part is home, second part is away
                        home_score = int(parts[0].strip())
                        away_score = int(parts[1].strip())
                        return home_score, away_score
                    except (ValueError, TypeError):
                        continue
        
        # If no separator found or parsing failed, return None
        logger.warning(f"Could not parse score string: {score_str}")
        return None, None

    def _fix_swapped_scores_if_needed(
        self,
        outcome: EventOutcome,
        match_data: dict,
        home_team: str,
        away_team: str,
    ) -> bool:
        """
        Check if scores in an existing outcome are swapped and fix them if needed.
        
        Args:
            outcome: Existing EventOutcome to check
            match_data: Match data from SLAPI API
            home_team: Home team name
            away_team: Away team name
            
        Returns:
            True if scores were fixed, False otherwise
        """
        metadata = outcome.metadata or {}
        stored_home_score = metadata.get('home_score')
        stored_away_score = metadata.get('away_score')
        
        if stored_home_score is None or stored_away_score is None:
            return False
        
        # Extract correct scores from API data
        correct_home_score, correct_away_score = self._extract_scores(match_data)
        
        if correct_home_score is None or correct_away_score is None:
            return False
        
        # Check if scores are swapped
        if stored_home_score != correct_home_score or stored_away_score != correct_away_score:
            # Scores are swapped - fix them
            logger.info(
                f'Fixing swapped scores for {outcome.prediction_event.name}: '
                f'old home={stored_home_score}, away={stored_away_score} -> '
                f'new home={correct_home_score}, away={correct_away_score}'
            )
            
            # Update metadata with correct scores
            metadata['home_score'] = correct_home_score
            metadata['away_score'] = correct_away_score
            
            # Update score string if it exists
            score_str = match_data.get('score')
            if score_str:
                metadata['score_string'] = score_str
            else:
                metadata['score_string'] = f"{correct_home_score}:{correct_away_score}"
            
            # Recalculate winner if needed
            if correct_home_score > correct_away_score:
                winning_team_name = home_team
            elif correct_away_score > correct_home_score:
                winning_team_name = away_team
            else:
                # Tie - shouldn't happen if we have an outcome, but handle it
                logger.warning(f'Match {outcome.prediction_event.name} has a tie score')
                return False
            
            # Find the correct winning option
            winning_option = outcome.prediction_event.options.filter(
                option__name=winning_team_name,
                is_active=True
            ).first()
            
            if winning_option:
                # Update outcome with correct scores and winner
                outcome.metadata = metadata
                outcome.winning_option = winning_option
                outcome.winning_generic_option = winning_option.option
                outcome.notes = (
                    f'Auto-generated from match result. Final score: '
                    f'{home_team} {correct_home_score}, {away_team} {correct_away_score}'
                )
                outcome.save(update_fields=['metadata', 'winning_option', 'winning_generic_option', 'notes'])
                
                # Re-score the event since the winner might have changed
                try:
                    from hooptipp.predictions.scoring_service import score_event_outcome
                    score_event_outcome(outcome)
                    logger.info(f'Re-scored event after fixing swapped scores: {outcome.prediction_event.name}')
                except Exception as e:
                    logger.warning(f'Failed to re-score event after fixing swapped scores: {e}')
                
                return True
        
        return False

    def _create_or_fix_outcome_for_past_match(
        self,
        event: PredictionEvent,
        match_id: str,
        match_data: dict,
        client,
        home_team: str,
        away_team: str,
        result: EventSourceResult,
    ) -> None:
        """
        Create an outcome for a past match if it has results and no outcome exists.
        If an outcome exists, check and fix swapped scores if needed.
        
        According to SLAPI API spec, matches from /leagues/{league_id}/matches include:
        - score_home: nullable integer - explicit home team score
        - score_away: nullable integer - explicit away team score
        - score: nullable string (e.g., "85:78") - score string for backwards compatibility
        - is_finished: boolean
        - is_cancelled: boolean
        
        Args:
            event: The prediction event for this match
            match_id: The match ID from SLAPI
            match_data: Match data from get_league_matches
            client: SLAPI client instance (not used, kept for compatibility)
            home_team: Home team name
            away_team: Away team name
            result: EventSourceResult to track outcome creation
        """
        # Check if outcome already exists
        existing_outcome = EventOutcome.objects.filter(prediction_event=event).first()
        if existing_outcome:
            # Check and fix swapped scores if needed
            self._fix_swapped_scores_if_needed(existing_outcome, match_data, home_team, away_team)
            return

        # Check if match is finished using is_finished flag from API
        is_finished = match_data.get('is_finished', False)
        
        # Also check if match is cancelled (cancelled matches shouldn't have outcomes)
        if match_data.get('is_cancelled', False):
            return

        # If not finished, check if match is past deadline (might be finished but flag not set)
        if not is_finished:
            if event.deadline < timezone.now() - timedelta(hours=3):
                # Match is past deadline, consider it finished if we have scores
                if match_data.get('score_home') is not None or match_data.get('score') or match_data.get('score_away') is not None:
                    is_finished = True
                else:
                    return  # No score available, can't create outcome
            else:
                return  # Match not finished and not past deadline

        if not is_finished:
            return

        # Extract scores using explicit fields (preferred) or parsing score string (fallback)
        home_score, away_score = self._extract_scores(match_data)
        
        if home_score is None or away_score is None:
            logger.warning(f'Could not extract scores for match {match_id}')
            return
        
        # Get score string for metadata (use explicit fields if available, otherwise use score string)
        score_str = match_data.get('score') or f"{home_score}:{away_score}"

        # Determine winner
        if home_score > away_score:
            winning_team_name = home_team
        elif away_score > home_score:
            winning_team_name = away_team
        else:
            # Tie - skip creating outcome
            logger.info(f'Match {match_id} ended in a tie, skipping outcome creation')
            return

        # Find the winning prediction option
        winning_option = event.options.filter(
            option__name=winning_team_name,
            is_active=True
        ).first()

        if not winning_option:
            logger.warning(f'Could not find prediction option for {winning_team_name} in event {event.name}')
            return

        # Create the EventOutcome
        try:
            with transaction.atomic():
                # Store match result data in metadata
                match_result_metadata = {
                    'away_score': away_score,
                    'home_score': home_score,
                    'away_team': away_team,
                    'home_team': home_team,
                    'is_finished': match_data.get('is_finished', True),
                    'is_cancelled': match_data.get('is_cancelled', False),
                    'is_confirmed': match_data.get('is_confirmed', False),
                    'match_id': match_id,
                    'score_string': score_str,
                }

                EventOutcome.objects.create(
                    prediction_event=event,
                    winning_option=winning_option,
                    winning_generic_option=winning_option.option,
                    resolved_at=timezone.now(),
                    metadata=match_result_metadata,
                    notes=f'Auto-generated from match result. Final score: {home_team} {home_score}, {away_team} {away_score}'
                )
                
                logger.info(f'Created outcome for past match: {event.name} -> {winning_option.label}')
        except Exception as e:
            logger.exception(f'Error creating outcome for match {match_id}: {e}')

