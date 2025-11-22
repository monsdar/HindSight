"""
Management command to update DBB matches.

Fetches latest matches for all tracked leagues and updates/creates
match records and prediction events.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from hooptipp.dbb.client import build_slapi_client
from hooptipp.dbb.models import TrackedLeague
from hooptipp.dbb.event_source import DbbEventSource
from hooptipp.predictions.models import EventOutcome

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Update DBB matches for all tracked leagues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--league-id',
            type=str,
            help='Only update matches for a specific league ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        league_id = options.get('league_id')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Check if SLAPI is configured
        client = build_slapi_client()
        if not client:
            self.stdout.write(
                self.style.ERROR('SLAPI is not configured. Set SLAPI_API_TOKEN environment variable.')
            )
            return

        # Get tracked leagues
        if league_id:
            tracked_leagues = TrackedLeague.objects.filter(league_id=league_id, is_active=True)
            if not tracked_leagues.exists():
                self.stdout.write(self.style.ERROR(f'No active tracked league found with ID: {league_id}'))
                return
        else:
            tracked_leagues = TrackedLeague.objects.filter(is_active=True)

        if not tracked_leagues.exists():
            self.stdout.write('No active tracked leagues found')
            return

        self.stdout.write(f'Found {tracked_leagues.count()} tracked league(s) to update')

        # Use the event source to sync events
        event_source = DbbEventSource()
        
        if dry_run:
            self.stdout.write('Would sync matches for tracked leagues')
            for league in tracked_leagues:
                self.stdout.write(f'  - {league.league_name} ({league.verband_name})')
        else:
            self.stdout.write('Syncing options (teams)...')
            options_result = event_source.sync_options()
            
            if options_result.has_errors:
                for error in options_result.errors:
                    self.stdout.write(self.style.ERROR(f'  Error: {error}'))
            
            if options_result.changed:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  Options: {options_result.options_created} created, '
                        f'{options_result.options_updated} updated'
                    )
                )
            else:
                self.stdout.write('  No option changes')

            self.stdout.write('Syncing events (matches)...')
            events_result = event_source.sync_events()
            
            if events_result.has_errors:
                for error in events_result.errors:
                    self.stdout.write(self.style.ERROR(f'  Error: {error}'))
            
            if events_result.changed:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  Events: {events_result.events_created} created, '
                        f'{events_result.events_updated} updated'
                    )
                )
            else:
                self.stdout.write('  No event changes')

            # Check for and fix swapped scores in existing outcomes
            self.stdout.write('Checking for swapped scores in existing outcomes...')
            fixed_count = self._fix_swapped_scores(event_source, dry_run)
            
            if fixed_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'  Fixed {fixed_count} outcome(s) with swapped scores')
                )
            else:
                self.stdout.write('  No swapped scores found')

            self.stdout.write(self.style.SUCCESS('Match update completed'))

    def _fix_swapped_scores(self, event_source: DbbEventSource, dry_run: bool) -> int:
        """
        Check all DBB outcomes and fix swapped scores using fresh data from SLAPI.
        
        Args:
            event_source: DbbEventSource instance
            dry_run: If True, only report what would be fixed
            
        Returns:
            Number of outcomes fixed
        """
        if not event_source.is_configured():
            return 0
        
        client = build_slapi_client()
        if not client:
            return 0
        
        fixed_count = 0
        
        # Get all DBB outcomes
        outcomes = EventOutcome.objects.filter(
            prediction_event__source_id='dbb-slapi'
        ).select_related('prediction_event')
        
        # Group outcomes by league for efficient API calls
        outcomes_by_league = {}
        for outcome in outcomes:
            event = outcome.prediction_event
            league_id = event.metadata.get('league_id')
            if league_id:
                if league_id not in outcomes_by_league:
                    outcomes_by_league[league_id] = []
                outcomes_by_league[league_id].append(outcome)
        
        # Process each league
        for league_id, league_outcomes in outcomes_by_league.items():
            try:
                # Fetch current match data from API
                matches = client.get_league_matches(league_id)
                match_dict = {str(m.get('match_id', '')): m for m in matches}
                
                # Check each outcome
                for outcome in league_outcomes:
                    event = outcome.prediction_event
                    match_id = event.source_event_id
                    match_data = match_dict.get(str(match_id))
                    
                    if not match_data:
                        continue
                    
                    # Extract team names from match data
                    home_team_obj = match_data.get('home_team', {})
                    away_team_obj = match_data.get('away_team', {})
                    
                    if isinstance(home_team_obj, dict):
                        home_team = home_team_obj.get('name', '')
                    else:
                        home_team = home_team_obj or ''
                    
                    if isinstance(away_team_obj, dict):
                        away_team = away_team_obj.get('name', '')
                    else:
                        away_team = away_team_obj or ''
                    
                    if not home_team or not away_team:
                        continue
                    
                    # Check and fix swapped scores
                    if not dry_run:
                        if event_source._fix_swapped_scores_if_needed(outcome, match_data, home_team, away_team):
                            fixed_count += 1
                    else:
                        # In dry-run, just check if scores would be fixed
                        metadata = outcome.metadata or {}
                        stored_home = metadata.get('home_score')
                        stored_away = metadata.get('away_score')
                        
                        if stored_home is not None and stored_away is not None:
                            correct_home, correct_away = event_source._extract_scores(match_data)
                            if correct_home is not None and correct_away is not None:
                                if stored_home != correct_home or stored_away != correct_away:
                                    self.stdout.write(
                                        f'  Would fix: {event.name} '
                                        f'(home: {stored_home}->{correct_home}, '
                                        f'away: {stored_away}->{correct_away})'
                                    )
                                    fixed_count += 1
                        
            except Exception as e:
                logger.warning(f'Error checking swapped scores for league {league_id}: {e}')
                continue
        
        return fixed_count

