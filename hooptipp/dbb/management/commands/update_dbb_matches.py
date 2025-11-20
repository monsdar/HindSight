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

            self.stdout.write(self.style.SUCCESS('Match update completed'))

