"""
Management command to backfill metadata for existing EventOutcomes.

This command fetches live game data from the BallDontLie API to populate
metadata for EventOutcomes that were created before the metadata field was added.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
from django.utils import timezone

from hooptipp.predictions.models import EventOutcome
from hooptipp.nba.services import get_live_game_data

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backfill metadata for existing EventOutcomes with live game data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit the number of EventOutcomes to process',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Update EventOutcomes that already have metadata',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        force = options['force']
        
        # Get EventOutcomes to update
        queryset = EventOutcome.objects.filter(
            prediction_event__scheduled_game__isnull=False,
            prediction_event__source_id='nba-balldontlie'
        ).select_related('prediction_event__scheduled_game')
        
        if not force:
            # Only update EventOutcomes without metadata or with empty metadata
            queryset = queryset.filter(
                models.Q(metadata__isnull=True) | models.Q(metadata={})
            )
        
        if limit:
            queryset = queryset[:limit]
        
        outcomes_to_update = list(queryset)
        
        if not outcomes_to_update:
            self.stdout.write('No EventOutcomes found to update')
            return
        
        self.stdout.write(f'Found {len(outcomes_to_update)} EventOutcomes to update')
        
        # Batch fetch game data to minimize API calls
        try:
            game_data_map = self.batch_fetch_game_data(outcomes_to_update)
        except Exception as e:
            logger.exception(f'Failed to batch fetch game data: {e}')
            self.stdout.write(self.style.ERROR(f'Failed to fetch game data: {e}'))
            game_data_map = {}
        
        updated_count = 0
        error_count = 0
        skipped_count = 0
        
        for outcome in outcomes_to_update:
            try:
                result = self.update_eventoutcome_metadata_batched(outcome, game_data_map, dry_run)
                if result == 'updated':
                    updated_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'[OK] Updated: {outcome.prediction_event.name}')
                    )
                elif result == 'skipped':
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'[SKIP] Skipped: {outcome.prediction_event.name} (no live data)')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'[SKIP] Skipped: {outcome.prediction_event.name} (already has metadata)')
                    )
                    skipped_count += 1
            except Exception as e:
                error_count += 1
                logger.exception(f'Error updating {outcome.prediction_event.name}: {e}')
                self.stdout.write(
                    self.style.ERROR(f'[ERROR] Error updating {outcome.prediction_event.name}: {e}')
                )
        
        # Summary
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed: {updated_count} updated, {skipped_count} skipped, {error_count} errors'
            )
        )

    def update_eventoutcome_metadata(self, outcome: EventOutcome, dry_run: bool = False) -> Optional[str]:
        """
        Update metadata for a single EventOutcome.
        
        Returns:
            'updated' if metadata was updated
            'skipped' if no live data available or already has metadata
            None if there was an error
        """
        game = outcome.prediction_event.scheduled_game
        game_data = get_live_game_data(game.nba_game_id)
        
        # Check if we have live data
        if not game_data or not game_data.get('game_status'):
            return 'skipped'
        
        # Get scores
        home_score = game_data.get('home_score')
        away_score = game_data.get('away_score')
        game_status = game_data.get('game_status', 'Final')
        
        # Create metadata
        metadata = {
            'away_score': away_score,
            'home_score': home_score,
            'away_team': game.away_team_tricode,
            'home_team': game.home_team_tricode,
            'away_team_full': game.away_team,
            'home_team_full': game.home_team,
            'game_status': game_status,
            'nba_game_id': game.nba_game_id,
        }
        
        if dry_run:
            self.stdout.write(
                f'  Would update metadata: {outcome.prediction_event.name} '
                f'(Final: {game.away_team_tricode} {away_score}, {game.home_team_tricode} {home_score})'
            )
            return 'updated'
        
        # Update the EventOutcome
        with transaction.atomic():
            outcome.metadata = metadata
            outcome.save(update_fields=['metadata'])
        
        return 'updated'

    def batch_fetch_game_data(self, outcomes: list[EventOutcome]) -> dict[str, dict]:
        """
        Batch fetch game data for multiple EventOutcomes to minimize API calls.
        
        Args:
            outcomes: List of EventOutcomes to fetch data for
            
        Returns:
            Dictionary mapping nba_game_id to game data
        """
        from hooptipp.nba.services import _build_bdl_client
        from datetime import datetime, timedelta
        
        game_data_map = {}
        
        # Group outcomes by unique game IDs and collect team IDs and dates
        unique_game_ids = set()
        team_ids = set()
        dates = set()
        
        for outcome in outcomes:
            game = outcome.prediction_event.scheduled_game
            game_id = game.nba_game_id
            unique_game_ids.add(game_id)
            
            # Extract dates from the game
            if hasattr(game, 'game_date') and game.game_date:
                dates.add(game.game_date.strftime('%Y-%m-%d'))
            
            # Extract team IDs from the game
            # We need to map team names to BallDontLie team IDs
            # For now, we'll focus on date filtering which is more reliable
            # TODO: Add team ID mapping for even more precise filtering
        
        if not unique_game_ids:
            return game_data_map
        
        self.stdout.write(f'Fetching data for {len(unique_game_ids)} unique games...')
        
        try:
            client = _build_bdl_client()
            if client is None:
                self.stdout.write(self.style.ERROR('BallDontLie API client not available'))
                return game_data_map
            
            # Single API call with all dates and team IDs
            if dates:
                date_list = list(dates)
                self.stdout.write(f'Filtering by dates: {date_list}')
                
                # Single API call with all dates at once
                try:
                    response = client.nba.games.list(
                        per_page=100,
                        dates=date_list  # Pass all dates in one call
                    )
                    
                    # Process the response to extract game data
                    for game in getattr(response, "data", []) or []:
                        game_id = str(getattr(game, "id", ""))
                        if game_id in unique_game_ids:
                            game_data_map[game_id] = self._extract_game_data_from_response(game)
                            self.stdout.write(f'  Found data for game {game_id}')
                            
                except Exception as e:
                    logger.warning(f'Failed to fetch games for dates {date_list}: {e}')
                    # Fall back to individual date calls if the combined call fails
                    self.stdout.write('Falling back to individual date calls...')
                    for date_str in date_list:
                        try:
                            response = client.nba.games.list(
                                per_page=100,
                                dates=[date_str]
                            )
                            
                            for game in getattr(response, "data", []) or []:
                                game_id = str(getattr(game, "id", ""))
                                if game_id in unique_game_ids:
                                    game_data_map[game_id] = self._extract_game_data_from_response(game)
                                    self.stdout.write(f'  Found data for game {game_id}')
                        except Exception as e:
                            logger.warning(f'Failed to fetch games for date {date_str}: {e}')
                            continue
            else:
                # Fallback: fetch recent games and filter client-side
                self.stdout.write('No specific dates found, fetching recent games...')
                try:
                    response = client.nba.games.list(
                        per_page=100,
                        # Fetch recent games (last 30 days)
                        start_date=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                        end_date=datetime.now().strftime('%Y-%m-%d')
                    )
                    
                    # Process the response to extract game data
                    for game in getattr(response, "data", []) or []:
                        game_id = str(getattr(game, "id", ""))
                        if game_id in unique_game_ids:
                            game_data_map[game_id] = self._extract_game_data_from_response(game)
                            self.stdout.write(f'  Found data for game {game_id}')
                except Exception as e:
                    logger.warning(f'Failed to fetch recent games: {e}')
            
            # If we still don't have all the games we need, fall back to individual calls
            missing_games = unique_game_ids - set(game_data_map.keys())
            if missing_games:
                self.stdout.write(f'Fetching {len(missing_games)} remaining games individually...')
                for game_id in missing_games:
                    try:
                        response = client.nba.games.get(int(game_id))
                        game = getattr(response, "data", None)
                        if game:
                            game_data_map[game_id] = self._extract_game_data_from_response(game)
                            self.stdout.write(f'  Found data for game {game_id}')
                    except Exception as e:
                        logger.warning(f'Failed to fetch data for game {game_id}: {e}')
                        continue
                        
        except Exception as e:
            logger.exception(f'Failed to batch fetch game data: {e}')
            self.stdout.write(self.style.ERROR(f'Failed to fetch game data: {e}'))
        
        self.stdout.write(f'Successfully fetched data for {len(game_data_map)} games')
        return game_data_map

    def _extract_game_data_from_response(self, game) -> dict:
        """
        Extract game data from BallDontLie API response.
        
        Args:
            game: Game object from BallDontLie API
            
        Returns:
            Dictionary with game data
        """
        # Extract scores
        home_score = getattr(game, "home_team_score", None)
        away_score = getattr(game, "visitor_team_score", None)
        
        # Extract status
        status = getattr(game, "status", "")
        
        # Determine if game is live
        status_lower = str(status).lower()
        is_live = any(
            keyword in status_lower
            for keyword in ["q1", "q2", "q3", "q4", "ot", "halftime"]
        )
        
        return {
            "away_score": away_score,
            "home_score": home_score,
            "game_status": status,
            "is_live": is_live,
        }

    def update_eventoutcome_metadata_batched(self, outcome: EventOutcome, game_data_map: dict[str, dict], dry_run: bool = False) -> Optional[str]:
        """
        Update metadata for a single EventOutcome using pre-fetched game data.
        
        Args:
            outcome: EventOutcome to update
            game_data_map: Pre-fetched game data mapping
            dry_run: If True, don't actually update the database
            
        Returns:
            'updated' if metadata was updated
            'skipped' if no live data available or already has metadata
            None if there was an error
        """
        game = outcome.prediction_event.scheduled_game
        game_id = game.nba_game_id
        
        # Get pre-fetched game data
        game_data = game_data_map.get(game_id)
        
        # Check if we have live data
        if not game_data or not game_data.get('game_status'):
            return 'skipped'
        
        # Get scores
        home_score = game_data.get('home_score')
        away_score = game_data.get('away_score')
        game_status = game_data.get('game_status', 'Final')
        
        # Create metadata
        metadata = {
            'away_score': away_score,
            'home_score': home_score,
            'away_team': game.away_team_tricode,
            'home_team': game.home_team_tricode,
            'away_team_full': game.away_team,
            'home_team_full': game.home_team,
            'game_status': game_status,
            'nba_game_id': game.nba_game_id,
        }
        
        if dry_run:
            self.stdout.write(
                f'  Would update metadata: {outcome.prediction_event.name} '
                f'(Final: {game.away_team_tricode} {away_score}, {game.home_team_tricode} {home_score})'
            )
            return 'updated'
        
        # Update the EventOutcome
        with transaction.atomic():
            outcome.metadata = metadata
            outcome.save(update_fields=['metadata'])
        
        return 'updated'
