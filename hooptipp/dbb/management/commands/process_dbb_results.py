"""
Management command to process completed DBB matches and create EventOutcome records.

This command checks for DBB matches that have ended and automatically creates
EventOutcome records for prediction events that don't have outcomes yet.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from hooptipp.predictions.models import EventOutcome, PredictionEvent, PredictionOption
from hooptipp.dbb.models import DbbMatch
from hooptipp.dbb.client import build_slapi_client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process completed DBB matches and create EventOutcome records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes',
        )
        parser.add_argument(
            '--hours-back',
            type=int,
            default=72,
            help='Look back N hours for completed matches (default: 72)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        hours_back = options['hours_back']

        cutoff_time = timezone.now() - timedelta(hours=hours_back)

        self.stdout.write(f'Looking for completed matches since {cutoff_time}')

        # Check if SLAPI is configured
        client = build_slapi_client()
        if not client:
            self.stdout.write(
                self.style.ERROR('SLAPI is not configured. Set SLAPI_API_TOKEN environment variable.')
            )
            return

        # Find DBB prediction events that are past deadline but have no outcome
        events_to_process = PredictionEvent.objects.filter(
            source_id='dbb-slapi',
            deadline__lt=timezone.now(),
            deadline__gte=cutoff_time,
            outcome__isnull=True,
            is_active=True,
        ).order_by('deadline')

        if not events_to_process.exists():
            self.stdout.write('No events found that need processing')
            return

        self.stdout.write(f'Found {events_to_process.count()} events to process')

        processed_count = 0
        error_count = 0
        skipped_count = 0

        for event in events_to_process:
            try:
                match_id = event.source_event_id
                
                # Fetch match details from SLAPI
                try:
                    match_data = client.get_match_details(match_id)
                except Exception as e:
                    logger.warning(f'Failed to fetch match data for {match_id}: {e}')
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'[SKIP] Skipped: {event.name} (API error)')
                    )
                    continue

                result = self.process_single_match(event, match_data, dry_run)
                
                if result == 'processed':
                    processed_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'[OK] Processed: {event.name}')
                    )
                elif result == 'skipped':
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'[SKIP] Skipped: {event.name} (match not final)')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'[SKIP] Skipped: {event.name} (no valid outcome)')
                    )
                    skipped_count += 1
                    
            except Exception as e:
                error_count += 1
                logger.exception(f'Error processing {event.name}: {e}')
                self.stdout.write(
                    self.style.ERROR(f'[ERROR] Error processing {event.name}: {e}')
                )

        # Summary
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed: {processed_count} processed, {skipped_count} skipped, {error_count} errors'
            )
        )

    def process_single_match(
        self, event: PredictionEvent, match_data: dict, dry_run: bool = False
    ) -> Optional[str]:
        """
        Process a single match and create EventOutcome if match is final.

        Args:
            event: PredictionEvent to process
            match_data: Dictionary with match data from SLAPI
            dry_run: If True, don't actually create outcomes

        Returns:
            'processed' if outcome was created
            'skipped' if match is not final or no valid outcome
            None if there was an error
        """
        # Check if match is finished
        status = match_data.get('status', '').lower()
        is_final = 'final' in status or 'finished' in status or 'ended' in status
        
        if not is_final:
            # Also check if we have scores
            home_score = match_data.get('home_score') or match_data.get('homeScore')
            away_score = match_data.get('away_score') or match_data.get('awayScore')
            
            # If we have scores and the match is past its time, consider it finished
            if home_score is not None and away_score is not None:
                if event.deadline < timezone.now() - timedelta(hours=3):
                    is_final = True

        if not is_final:
            return 'skipped'

        # Get scores
        home_score = match_data.get('home_score') or match_data.get('homeScore')
        away_score = match_data.get('away_score') or match_data.get('awayScore')

        if home_score is None or away_score is None:
            logger.warning(f'Match {match_data.get("id")} is final but missing scores')
            return 'skipped'

        # Convert to int
        try:
            home_score = int(home_score)
            away_score = int(away_score)
        except (ValueError, TypeError):
            logger.warning(f'Invalid scores for match {match_data.get("id")}')
            return 'skipped'

        # Determine winner
        # Note: home_team and away_team are objects with structure {"id": "...", "name": "...", ...}
        home_team_obj = match_data.get('home_team', {})
        away_team_obj = match_data.get('away_team', {}) or match_data.get('visitor_team', {})
        
        if isinstance(home_team_obj, dict):
            home_team = home_team_obj.get('name', '')
        else:
            home_team = home_team_obj or ''
        
        if isinstance(away_team_obj, dict):
            away_team = away_team_obj.get('name', '')
        else:
            away_team = away_team_obj or ''

        if home_score > away_score:
            winning_team_name = home_team
        elif away_score > home_score:
            winning_team_name = away_team
        else:
            logger.warning(f'Match {match_data.get("match_id")} ended in a tie')
            return 'skipped'

        # Find the winning prediction option
        winning_option = event.options.filter(
            option__name=winning_team_name,
            is_active=True
        ).first()

        if not winning_option:
            logger.warning(f'Could not find prediction option for {winning_team_name} in event {event.name}')
            return 'skipped'

        if dry_run:
            self.stdout.write(
                f'  Would create outcome: {event.name} -> {winning_option.label} '
                f'(Final: {away_team} {away_score}, {home_team} {home_score})'
            )
            return 'processed'

        # Create the EventOutcome
        with transaction.atomic():
            # Store match result data in metadata
            match_result_metadata = {
                'away_score': away_score,
                'home_score': home_score,
                'away_team': away_team,
                'home_team': home_team,
                'match_status': match_data.get('status', 'Final'),
                'match_id': match_data.get('id', ''),
            }

            outcome = EventOutcome.objects.create(
                prediction_event=event,
                winning_option=winning_option,
                winning_generic_option=winning_option.option,
                resolved_at=timezone.now(),
                metadata=match_result_metadata,
                notes=f'Auto-generated from match result. Final score: {away_team} {away_score}, {home_team} {home_score}'
            )

            # Auto-score the event
            try:
                from hooptipp.predictions.scoring_service import score_event_outcome
                score_result = score_event_outcome(outcome)

                if score_result.created_count or score_result.updated_count:
                    self.stdout.write(
                        f'  Auto-scored: {score_result.created_count} created, {score_result.updated_count} updated scores'
                    )
                else:
                    self.stdout.write('  Auto-scored: No new scores (already scored)')

            except Exception as e:
                logger.warning(f'Failed to auto-score {event.name}: {e}')
                self.stdout.write(f'  Warning: Failed to auto-score: {e}')

        return 'processed'

