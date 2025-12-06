"""
Management command to process and award achievements to users.

This command processes different types of achievements (season rankings,
registration milestones, etc.) and creates/updates achievement records.
Designed to be run periodically via cron job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.db.models.functions import Coalesce

from hooptipp.predictions.models import Achievement, Season, UserEventScore

logger = logging.getLogger(__name__)


@dataclass
class AchievementProcessorResult:
    """Result of processing achievements for a specific type."""
    achievement_type: str
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class Command(BaseCommand):
    help = 'Process and award achievements to users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Recalculate all achievements (may create duplicates if not careful)',
        )
        parser.add_argument(
            '--type',
            type=str,
            help='Process only a specific achievement type (e.g., "season_gold")',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        achievement_type = options.get('type')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
            self.stdout.write('')

        # Get list of processors
        processors = self._get_processors()

        # Filter by type if specified
        if achievement_type:
            processors = {k: v for k, v in processors.items() if k == achievement_type}
            if not processors:
                self.stdout.write(
                    self.style.ERROR(f'No processor found for achievement type: {achievement_type}')
                )
                return

        # Process each achievement type
        total_created = 0
        total_updated = 0
        total_skipped = 0
        all_errors = []

        for achievement_type_key, processor_func in processors.items():
            self.stdout.write(f'Processing {achievement_type_key} achievements...')
            
            try:
                result = processor_func(dry_run=dry_run, force=force)
                total_created += result.created
                total_updated += result.updated
                total_skipped += result.skipped
                all_errors.extend(result.errors)
                
                if result.errors:
                    for error in result.errors:
                        self.stdout.write(self.style.ERROR(f'  ERROR: {error}'))
                
                if dry_run:
                    self.stdout.write(
                        f'  Would create: {result.created}, '
                        f'update: {result.updated}, skip: {result.skipped}'
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  Created: {result.created}, '
                            f'updated: {result.updated}, skipped: {result.skipped}'
                        )
                    )
            except Exception as e:
                logger.exception(f'Error processing {achievement_type_key} achievements: {e}')
                self.stdout.write(
                    self.style.ERROR(f'  ERROR processing {achievement_type_key}: {e}')
                )
                all_errors.append(f'{achievement_type_key}: {str(e)}')

        # Summary
        self.stdout.write('')
        if all_errors:
            self.stdout.write(self.style.WARNING(f'Completed with {len(all_errors)} error(s)'))
        else:
            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'DRY RUN complete. Would create: {total_created}, '
                        f'update: {total_updated}, skip: {total_skipped}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Complete. Created: {total_created}, '
                        f'updated: {total_updated}, skipped: {total_skipped}'
                    )
                )

    def _get_processors(self) -> dict[str, callable]:
        """Get dictionary of achievement processors."""
        return {
            'season_achievements': self._process_season_achievements,
            'beta_tester': self._process_beta_tester_achievements,
        }

    def _process_season_achievements(
        self,
        dry_run: bool = False,
        force: bool = False,
    ) -> AchievementProcessorResult:
        """
        Process season achievements (Gold, Silver, Bronze for top 3 finishers).
        
        This method processes all three medal types in one pass for efficiency.
        """
        result = AchievementProcessorResult(achievement_type='season_achievements')
        
        # Get all completed seasons (end_date < today)
        today = timezone.now().date()
        completed_seasons = Season.objects.filter(end_date__lt=today).order_by('-end_date')
        
        if not completed_seasons.exists():
            result.skipped = 1
            return result

        # Achievement type configuration
        achievement_configs = [
            {
                'type': Achievement.AchievementType.SEASON_GOLD,
                'rank': 1,
                'name': 'Season Champion',
                'description': 'Finished in 1st place',
                'emoji': '🥇',
            },
            {
                'type': Achievement.AchievementType.SEASON_SILVER,
                'rank': 2,
                'name': 'Season Runner-Up',
                'description': 'Finished in 2nd place',
                'emoji': '🥈',
            },
            {
                'type': Achievement.AchievementType.SEASON_BRONZE,
                'rank': 3,
                'name': 'Season Third Place',
                'description': 'Finished in 3rd place',
                'emoji': '🥉',
            },
        ]

        with transaction.atomic():
            for season in completed_seasons:
                # Calculate rankings for this season
                rankings = self._calculate_season_rankings(season)
                
                if not rankings:
                    continue
                
                # Award achievements for each rank
                for config in achievement_configs:
                    rank = config['rank']
                    
                    # Get all users at this rank (handles ties)
                    users_at_rank = [
                        user_data for user_data in rankings
                        if user_data['rank'] == rank
                    ]
                    
                    if not users_at_rank:
                        continue
                    
                    # Award achievement to all users at this rank
                    for user_data in users_at_rank:
                        user = user_data['user']
                        
                        # Check if achievement already exists
                        existing = Achievement.objects.filter(
                            user=user,
                            season=season,
                            achievement_type=config['type']
                        ).first()
                        
                        if existing and not force:
                            result.skipped += 1
                            continue
                        
                        if dry_run:
                            result.created += 1
                            continue
                        
                        # Create or update achievement
                        achievement, created = Achievement.objects.update_or_create(
                            user=user,
                            season=season,
                            achievement_type=config['type'],
                            defaults={
                                'name': config['name'],
                                'description': f"{config['description']} in {season.name}",
                                'emoji': config['emoji'],
                            }
                        )
                        
                        if created:
                            result.created += 1
                        else:
                            result.updated += 1

        return result

    def _calculate_season_rankings(self, season: Season) -> list[dict]:
        """
        Calculate user rankings for a season based on total points.
        
        Returns list of dicts with 'user', 'total_points', and 'rank' keys.
        Handles ties by assigning the same rank to users with equal points.
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Get all scores within season timeframe
        # Use datetime objects for proper timezone-aware comparison
        from datetime import datetime as dt, time as dt_time
        season_start_datetime = timezone.make_aware(
            dt.combine(season.start_date, dt.min.time())
        )
        # Use end of day (23:59:59) for season end to include all scores on that day
        season_end_datetime = timezone.make_aware(
            dt.combine(season.end_date, dt_time(23, 59, 59))
        )
        season_scores = UserEventScore.objects.filter(
            awarded_at__gte=season_start_datetime,
            awarded_at__lte=season_end_datetime
        )
        
        # Calculate total points per user
        user_totals = (
            season_scores
            .values('user')
            .annotate(
                total_points=Coalesce(Sum('points_awarded'), 0),
                event_count=Count('prediction_event', distinct=True)
            )
            .order_by('-total_points', '-event_count', 'user__username')
        )
        
        # Convert to list and assign ranks (handling ties)
        rankings = []
        current_rank = 1
        previous_points = None
        previous_event_count = None
        
        for user_data in user_totals:
            user_id = user_data['user']
            total_points = int(user_data['total_points'])
            event_count = int(user_data['event_count'])
            
            # Check if this is a tie with previous user
            if (
                previous_points is not None and
                previous_points == total_points and
                previous_event_count == event_count
            ):
                # Same rank as previous user (tie)
                rank = current_rank
            else:
                # New rank (number of users processed so far)
                rank = len(rankings) + 1
                current_rank = rank
            
            # Get user object
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                continue
            
            rankings.append({
                'user': user,
                'total_points': total_points,
                'event_count': event_count,
                'rank': rank,
            })
            
            previous_points = total_points
            previous_event_count = event_count
        
        return rankings

    def _process_beta_tester_achievements(
        self,
        dry_run: bool = False,
        force: bool = False,
    ) -> AchievementProcessorResult:
        """
        Process beta tester achievements for users registered before December 20, 2025.
        """
        result = AchievementProcessorResult(achievement_type='beta_tester')
        
        from django.contrib.auth import get_user_model
        from datetime import datetime, date
        User = get_user_model()
        
        # Beta tester cutoff date: December 20, 2025
        beta_cutoff_date = date(2025, 12, 20)
        beta_cutoff_datetime = timezone.make_aware(
            datetime.combine(beta_cutoff_date, datetime.min.time())
        )
        
        # Find all users registered before the cutoff date
        beta_users = User.objects.filter(date_joined__lt=beta_cutoff_datetime)
        
        if not beta_users.exists():
            result.skipped = 1
            return result
        
        achievement_config = {
            'type': Achievement.AchievementType.BETA_TESTER,
            'name': 'Beta Tester',
            'description': 'Participated in the BiBATiPP Betatest',
            'emoji': '🏅',
        }
        
        with transaction.atomic():
            for user in beta_users:
                # Check if achievement already exists
                existing = Achievement.objects.filter(
                    user=user,
                    season=None,  # Beta tester is not season-specific
                    achievement_type=achievement_config['type']
                ).first()
                
                if existing and not force:
                    result.skipped += 1
                    continue
                
                if dry_run:
                    result.created += 1
                    continue
                
                # Create or update achievement
                achievement, created = Achievement.objects.update_or_create(
                    user=user,
                    season=None,
                    achievement_type=achievement_config['type'],
                    defaults={
                        'name': achievement_config['name'],
                        'description': achievement_config['description'],
                        'emoji': achievement_config['emoji'],
                    }
                )
                
                if created:
                    result.created += 1
                else:
                    result.updated += 1
        
        return result

