"""
Management command to process scores for prediction events with outcomes.

This command processes scores for all user tips that have corresponding event outcomes,
similar to the admin action but with time-based filtering and automation support.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from hooptipp.predictions.models import EventOutcome, PredictionEvent
from hooptipp.predictions.scoring_service import process_all_user_scores, ProcessAllScoresResult

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process scores for prediction events with outcomes'

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
            help='Look back N hours for events with outcomes (default: 24)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Delete existing scores and recalculate from scratch',
        )
        parser.add_argument(
            '--force-automation',
            action='store_true',
            help='Process scores even if automation is disabled via environment variable',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        hours_back = options['hours_back']
        force = options['force']
        force_automation = options['force_automation']
        
        # Check if automation is enabled
        if not force_automation and not self._is_automation_enabled():
            self.stdout.write(
                self.style.WARNING('Score processing is disabled via AUTO_PROCESS_SCORES environment variable')
            )
            return
        
        # Get hours back from environment or use provided value
        hours_back = int(os.getenv('SCORE_PROCESSING_HOURS_BACK', hours_back))
        cutoff_time = timezone.now() - timezone.timedelta(hours=hours_back)
        
        self.stdout.write(f'Looking for events with outcomes since {cutoff_time}')
        
        # Find events with outcomes that need scoring
        events_to_process = self._get_events_to_process(cutoff_time)
        
        if not events_to_process.exists():
            self.stdout.write('No events found that need score processing')
            return
        
        self.stdout.write(f'Found {events_to_process.count()} events with outcomes to process')
        
        if dry_run:
            self._show_dry_run_summary(events_to_process)
            return
        
        # Process scores
        try:
            result = self._process_scores(events_to_process, force)
            self._show_results(result)
        except Exception as e:
            logger.exception(f'Error processing scores: {e}')
            self.stdout.write(
                self.style.ERROR(f'✗ Error processing scores: {e}')
            )
            raise CommandError(f'Score processing failed: {e}')

    def _is_automation_enabled(self) -> bool:
        """Check if automation is enabled via environment variable."""
        return os.getenv('AUTO_PROCESS_SCORES', 'true').lower() == 'true'

    def _get_events_to_process(self, cutoff_time):
        """Get events with outcomes that need score processing."""
        return PredictionEvent.objects.filter(
            outcome__isnull=False,
            outcome__resolved_at__gte=cutoff_time,
            is_active=True
        ).select_related('outcome').prefetch_related(
            'tips__user', 
            'tips__prediction_option', 
            'tips__selected_option'
        ).order_by('outcome__resolved_at')

    def _show_dry_run_summary(self, events_queryset):
        """Show what would be processed in dry run mode."""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
        self.stdout.write('')
        
        total_tips = 0
        total_outcomes = 0
        
        for event in events_queryset:
            tips_count = event.tips.count()
            total_tips += tips_count
            total_outcomes += 1
            
            outcome = event.outcome
            resolved_time = outcome.resolved_at.strftime('%Y-%m-%d %H:%M:%S')
            
            self.stdout.write(
                f'  {event.name} (resolved: {resolved_time}) - {tips_count} tips'
            )
        
        self.stdout.write('')
        self.stdout.write(
            f'Would process {total_outcomes} events with {total_tips} total tips'
        )

    def _process_scores(self, events_queryset, force: bool) -> ProcessAllScoresResult:
        """Process scores for the given events."""
        # We need to modify the scoring service to work with a subset of events
        # For now, we'll use the existing service but filter the results
        
        if force:
            # If force is True, we need to be more careful about what we delete
            # We'll only delete scores for events we're processing
            event_ids = list(events_queryset.values_list('id', flat=True))
            from hooptipp.predictions.models import UserEventScore
            UserEventScore.objects.filter(prediction_event_id__in=event_ids).delete()
        
        # Process scores using the existing service
        # Note: The current service processes ALL events with outcomes
        # We'll need to modify it or create a filtered version
        result = self._process_filtered_scores(events_queryset, force)
        
        return result

    def _process_filtered_scores(self, events_queryset, force: bool) -> ProcessAllScoresResult:
        """Process scores for a filtered set of events."""
        from hooptipp.predictions.models import UserEventScore, UserTip
        from hooptipp.predictions.scoring_service import (
            _tip_matches_outcome, _calculate_lock_multiplier, _outcome_has_selection
        )
        from hooptipp.predictions.lock_service import LockService
        
        total_events_processed = 0
        total_scores_created = 0
        total_scores_updated = 0
        total_tips_skipped = 0
        total_locks_returned = 0
        total_locks_forfeited = 0
        events_with_errors = []
        
        with transaction.atomic():
            for event in events_queryset:
                try:
                    outcome = event.outcome
                    if not _outcome_has_selection(outcome):
                        events_with_errors.append(f"{event.name}: No winning option specified")
                        continue
                    
                    total_events_processed += 1
                    
                    # Get all tips for this event
                    tips = list(event.tips.all())
                    
                    for tip in tips:
                        if not _tip_matches_outcome(tip, outcome):
                            # Handle incorrect predictions with locks - forfeit them
                            if tip.lock_status == UserTip.LockStatus.ACTIVE:
                                lock_service = LockService(tip.user)
                                lock_service.schedule_forfeit(tip, resolved_at=outcome.resolved_at)
                                total_locks_forfeited += 1
                            total_tips_skipped += 1
                            continue
                        
                        base_points = event.points
                        multiplier = _calculate_lock_multiplier(tip)
                        total_points = base_points * multiplier
                        defaults = {
                            'base_points': base_points,
                            'lock_multiplier': multiplier,
                            'points_awarded': total_points,
                            'is_lock_bonus': multiplier > 1,
                        }
                        
                        score, created = UserEventScore.objects.update_or_create(
                            user=tip.user,
                            prediction_event=event,
                            defaults=defaults,
                        )
                        
                        if created:
                            total_scores_created += 1
                        else:
                            total_scores_updated += 1
                        
                        # Return lock to user if they had an active lock
                        if tip.lock_status == UserTip.LockStatus.ACTIVE:
                            lock_service = LockService(tip.user)
                            lock_service.release_lock(tip)
                            total_locks_returned += 1
                    
                    # Mark outcome as scored
                    outcome.scored_at = timezone.now()
                    outcome.score_error = ''
                    outcome.save(update_fields=['scored_at', 'score_error'])
                    
                except Exception as e:
                    error_msg = f"{event.name}: {str(e)}"
                    events_with_errors.append(error_msg)
                    logger.exception(f'Error processing scores for {event.name}: {e}')
        
        return ProcessAllScoresResult(
            total_events_processed=total_events_processed,
            total_scores_created=total_scores_created,
            total_scores_updated=total_scores_updated,
            total_tips_skipped=total_tips_skipped,
            total_locks_returned=total_locks_returned,
            total_locks_forfeited=total_locks_forfeited,
            events_with_errors=events_with_errors,
        )

    def _show_results(self, result: ProcessAllScoresResult):
        """Display the results of score processing."""
        self.stdout.write('')
        
        if result.events_with_errors:
            self.stdout.write(self.style.WARNING('Events with errors:'))
            for error in result.events_with_errors:
                self.stdout.write(f'  ⚠ {error}')
            self.stdout.write('')
        
        if result.total_scores_created or result.total_scores_updated:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Successfully processed {result.total_events_processed} events. '
                    f'Created {result.total_scores_created} scores, '
                    f'updated {result.total_scores_updated} scores. '
                    f'Returned {result.total_locks_returned} locks to users, '
                    f'forfeited {result.total_locks_forfeited} locks. '
                    f'Skipped {result.total_tips_skipped} tips.'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'No scores were created or updated. '
                    f'Processed {result.total_events_processed} events, '
                    f'returned {result.total_locks_returned} locks to users, '
                    f'forfeited {result.total_locks_forfeited} locks, '
                    f'skipped {result.total_tips_skipped} tips.'
                )
            )
