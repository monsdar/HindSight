"""
Management command to send reminder emails to users about unpredicted events.

This command checks for users with active accounts who have unpredicted events
with deadlines in the next 24 hours and sends reminder emails.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import List

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from hooptipp.predictions.models import (
    PredictionEvent,
    Season,
    SeasonParticipant,
    UserPreferences,
    UserTip,
)
from hooptipp.predictions.reminder_emails import send_reminder_email

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Send reminder emails to users about unpredicted events with upcoming deadlines'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending emails',
        )
        parser.add_argument(
            '--force-send-user',
            type=str,
            help='Username of a user to send reminder email to, bypassing all filtering checks (for testing)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force_send_username = options.get('force_send_user')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No emails will be sent'))
            self.stdout.write('')

        now = timezone.now()
        
        emails_sent = 0
        users_skipped_no_recent_prediction = 0
        users_skipped_no_unpredicted_events = 0
        errors = []

        # Handle force-send-user flag first
        if force_send_username:
            try:
                forced_user = User.objects.get(username=force_send_username)
                self.stdout.write(
                    self.style.WARNING(
                        f'FORCE SEND MODE: Sending reminder to {forced_user.username} ({forced_user.email}) '
                        f'bypassing all filtering checks'
                    )
                )
                self.stdout.write('')

                # Get all unpredicted events in next 24 hours (no filtering)
                unpredicted_events = self._get_unpredicted_events(forced_user, now)

                if not unpredicted_events:
                    self.stdout.write(
                        self.style.WARNING(
                            f'No unpredicted events found for {forced_user.username} in the next 24 hours'
                        )
                    )
                else:
                    if dry_run:
                        self.stdout.write(
                            f'Would send reminder to {forced_user.username} ({forced_user.email}) '
                            f'for {len(unpredicted_events)} event(s):'
                        )
                        for event in unpredicted_events:
                            self.stdout.write(f'  - {event.name} (deadline: {event.deadline})')
                        self.stdout.write('')
                    else:
                        # Send reminder email (force mode - no filtering)
                        send_reminder_email(forced_user, unpredicted_events)
                        emails_sent += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'FORCE SENT reminder to {forced_user.username} ({forced_user.email}) '
                                f'for {len(unpredicted_events)} event(s)'
                            )
                        )

            except User.DoesNotExist:
                error_msg = f'User "{force_send_username}" not found'
                errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f'[ERROR] {error_msg}'))
                return
            except Exception as e:
                error_msg = f'Error processing forced user {force_send_username}: {str(e)}'
                errors.append(error_msg)
                logger.exception(error_msg)
                self.stdout.write(self.style.ERROR(f'[ERROR] {error_msg}'))
                return

            # If force-send-user is specified, don't process normal users
            self.stdout.write('')
            self.stdout.write('Summary:')
            if dry_run:
                self.stdout.write(f'  Would send: {emails_sent} email(s)')
            else:
                self.stdout.write(f'  Sent: {emails_sent} email(s)')
            if errors:
                self.stdout.write('')
                self.stdout.write(self.style.WARNING('Errors:'))
                for error in errors:
                    self.stdout.write(f'  [WARNING] {error}')
            return
        
        # Normal processing: Filter users: is_active=True, reminder_emails_enabled=True
        users_to_check = User.objects.filter(
            is_active=True,
            preferences__reminder_emails_enabled=True
        ).select_related('preferences')
        
        total_users = users_to_check.count()
        self.stdout.write(f'Checking {total_users} users for reminder emails...')
        self.stdout.write('')

        for user in users_to_check:
            try:
                # Find the most recent event (by deadline) that has already passed
                latest_passed_event = PredictionEvent.objects.filter(
                    is_active=True,
                    deadline__lt=now
                ).order_by('-deadline').first()

                # Only proceed if user has a UserTip for that event (prevents spamming inactive users)
                if latest_passed_event:
                    has_predicted_latest = UserTip.objects.filter(
                        user=user,
                        prediction_event=latest_passed_event
                    ).exists()
                    
                    if not has_predicted_latest:
                        users_skipped_no_recent_prediction += 1
                        continue

                # Find unpredicted events in next 24 hours
                unpredicted_events = self._get_unpredicted_events(user, now)
                
                # Filter by season enrollment if a season is active
                eligible_events = self._filter_by_season_enrollment(user, unpredicted_events, now)

                if not eligible_events:
                    users_skipped_no_unpredicted_events += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f'Would send reminder to {user.username} ({user.email}) '
                        f'for {len(eligible_events)} event(s):'
                    )
                    for event in eligible_events:
                        self.stdout.write(f'  - {event.name} (deadline: {event.deadline})')
                    self.stdout.write('')
                else:
                    # Send reminder email
                    send_reminder_email(user, eligible_events)
                    emails_sent += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Sent reminder to {user.username} ({user.email}) '
                            f'for {len(eligible_events)} event(s)'
                        )
                    )

            except Exception as e:
                error_msg = f'Error processing user {user.username}: {str(e)}'
                errors.append(error_msg)
                logger.exception(error_msg)
                self.stdout.write(self.style.ERROR(f'[ERROR] {error_msg}'))

        # Summary
        self.stdout.write('')
        self.stdout.write('Summary:')
        if dry_run:
            self.stdout.write(f'  Would send: {emails_sent} email(s)')
        else:
            self.stdout.write(f'  Sent: {emails_sent} email(s)')
        self.stdout.write(f'  Skipped (no recent prediction): {users_skipped_no_recent_prediction}')
        self.stdout.write(f'  Skipped (no unpredicted events): {users_skipped_no_unpredicted_events}')
        
        if errors:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Errors:'))
            for error in errors:
                self.stdout.write(f'  [WARNING] {error}')

    def _get_unpredicted_events(self, user: User, now) -> List[PredictionEvent]:
        """Get unpredicted events for a user in the next 24 hours."""
        next_24_hours = now + timedelta(hours=24)
        
        # Get events where:
        # - deadline is within next 24 hours
        # - is_active=True, opens_at <= now
        # - User has no UserTip for the event
        unpredicted_events = PredictionEvent.objects.filter(
            is_active=True,
            opens_at__lte=now,
            deadline__gte=now,
            deadline__lte=next_24_hours
        ).exclude(
            tips__user=user
        ).order_by('deadline')
        
        return list(unpredicted_events)

    def _filter_by_season_enrollment(
        self, user: User, events: List[PredictionEvent], now
    ) -> List[PredictionEvent]:
        """Filter events by season enrollment."""
        active_season = Season.get_active_season(check_datetime=now)
        
        if not active_season:
            # No active season - include all events (backward compatibility)
            return events
        
        # Get all seasons to check event membership
        all_seasons = Season.objects.exclude(
            start_date__isnull=True
        ).exclude(
            end_date__isnull=True
        )
        
        # Check if user is enrolled in active season
        is_enrolled_in_active = SeasonParticipant.objects.filter(
            user=user,
            season=active_season
        ).exists()
        
        # Filter events based on season enrollment
        eligible_events = []
        
        for event in events:
            # Find which season (if any) contains this event's deadline
            event_season = None
            for season in all_seasons:
                try:
                    if season.start_datetime <= event.deadline <= season.end_datetime:
                        event_season = season
                        break
                except (ValueError, AttributeError):
                    # Skip seasons with invalid data
                    continue
            
            if event_season is None:
                # Event doesn't belong to any season - include it (backward compatibility)
                eligible_events.append(event)
            elif event_season == active_season:
                # Event belongs to active season - check enrollment
                if is_enrolled_in_active:
                    eligible_events.append(event)
                # If not enrolled, skip this event
            # If event belongs to a different season (shouldn't happen if only one active), skip it
        
        return eligible_events

