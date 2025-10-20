"""
Management command to process completed NBA games and create EventOutcome records.

This command checks for NBA games that have ended and automatically creates
EventOutcome records for prediction events that don't have outcomes yet.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from hooptipp.predictions.models import EventOutcome, PredictionEvent, PredictionOption
from hooptipp.nba.models import ScheduledGame
from hooptipp.nba.services import get_live_game_data

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process completed NBA games and create EventOutcome records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes',
        )
        parser.add_argument(
            '--hours-back',
            type=int,
            default=24,
            help='Look back N hours for completed games (default: 24)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Process games even if automation is disabled via environment variable',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        hours_back = options['hours_back']
        force = options['force']
        
        # Check if automation is enabled
        if not force and not self._is_automation_enabled():
            self.stdout.write(
                self.style.WARNING('Game outcome processing is disabled via AUTO_PROCESS_GAME_OUTCOMES environment variable')
            )
            return
        
        # Get hours back from environment or use provided value
        hours_back = int(os.getenv('GAME_OUTCOME_PROCESSING_HOURS_BACK', hours_back))
        cutoff_time = timezone.now() - timezone.timedelta(hours=hours_back)
        
        self.stdout.write(f'Looking for completed games since {cutoff_time}')
        
        # Find NBA prediction events that are past deadline but have no outcome
        events_to_process = self._get_events_to_process(cutoff_time)
        
        if not events_to_process.exists():
            self.stdout.write('No events found that need processing')
            return
        
        self.stdout.write(f'Found {events_to_process.count()} events to process')
        
        processed_count = 0
        error_count = 0
        skipped_count = 0
        
        for event in events_to_process:
            try:
                result = self.process_single_game(event, dry_run)
                if result == 'processed':
                    processed_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Processed: {event.name}')
                    )
                elif result == 'skipped':
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'⚠ Skipped: {event.name} (game not final)')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'⚠ Skipped: {event.name} (no valid outcome)')
                    )
                    skipped_count += 1
            except Exception as e:
                error_count += 1
                logger.exception(f'Error processing {event.name}: {e}')
                self.stdout.write(
                    self.style.ERROR(f'✗ Error processing {event.name}: {e}')
                )
        
        # Summary
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed: {processed_count} processed, {skipped_count} skipped, {error_count} errors'
            )
        )

    def _is_automation_enabled(self) -> bool:
        """Check if automation is enabled via environment variable."""
        return os.getenv('AUTO_PROCESS_GAME_OUTCOMES', 'true').lower() == 'true'

    def _get_events_to_process(self, cutoff_time):
        """Get events that need processing."""
        return PredictionEvent.objects.filter(
            scheduled_game__isnull=False,
            deadline__lt=timezone.now(),
            deadline__gte=cutoff_time,
            outcome__isnull=True,
            is_active=True,
            source_id='nba-balldontlie'
        ).select_related('scheduled_game').prefetch_related('options__option').order_by('deadline')

    def process_single_game(self, event: PredictionEvent, dry_run: bool = False) -> Optional[str]:
        """
        Process a single game and create EventOutcome if game is final.
        
        Returns:
            'processed' if outcome was created
            'skipped' if game is not final or no valid outcome
            None if there was an error
        """
        game = event.scheduled_game
        game_data = get_live_game_data(game.nba_game_id)
        
        # Check if game is final
        status = game_data.get('game_status', '').lower()
        if 'final' not in status:
            return 'skipped'
        
        # Get scores
        home_score = game_data.get('home_score')
        away_score = game_data.get('away_score')
        
        if home_score is None or away_score is None:
            logger.warning(f'Game {game.nba_game_id} is final but missing scores')
            return 'skipped'
        
        # Determine winner
        if home_score > away_score:
            winning_team_abbr = game.home_team_tricode
        elif away_score > home_score:
            winning_team_abbr = game.away_team_tricode
        else:
            logger.warning(f'Game {game.nba_game_id} ended in a tie')
            return 'skipped'
        
        # Find the winning prediction option
        winning_option = event.options.filter(
            option__short_name=winning_team_abbr,
            is_active=True
        ).first()
        
        if not winning_option:
            logger.warning(f'Could not find prediction option for {winning_team_abbr} in event {event.name}')
            return 'skipped'
        
        if dry_run:
            self.stdout.write(
                f'  Would create outcome: {event.name} -> {winning_option.label} '
                f'(Final: {game.away_team_tricode} {away_score}, {game.home_team_tricode} {home_score})'
            )
            return 'processed'
        
        # Create the EventOutcome
        with transaction.atomic():
            outcome = EventOutcome.objects.create(
                prediction_event=event,
                winning_option=winning_option,
                winning_generic_option=winning_option.option,
                resolved_at=timezone.now(),
                notes=f'Auto-generated from game result. Final score: {game.away_team_tricode} {away_score}, {game.home_team_tricode} {home_score}'
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
