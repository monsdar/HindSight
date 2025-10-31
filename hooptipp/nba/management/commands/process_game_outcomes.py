"""
Management command to process completed NBA games and create EventOutcome records.

This command checks for NBA games that have ended and automatically creates
EventOutcome records for prediction events that don't have outcomes yet.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from hooptipp.predictions.models import EventOutcome, PredictionEvent, PredictionOption
from hooptipp.nba.models import ScheduledGame
from hooptipp.nba.services import _build_bdl_client
from hooptipp.nba.managers import NbaTeamManager

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
        
        # Batch fetch all game data in a single API call
        game_data_map = self.batch_fetch_game_data(events_to_process)
        
        processed_count = 0
        error_count = 0
        skipped_count = 0
        
        for event in events_to_process:
            try:
                game_id = event.scheduled_game.nba_game_id
                game_data = game_data_map.get(game_id)
                
                if game_data is None:
                    logger.warning(f'No game data found for game {game_id} (event: {event.name})')
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'[SKIP] Skipped: {event.name} (no game data available)')
                    )
                    continue
                
                result = self.process_single_game(event, game_data, dry_run)
                if result == 'processed':
                    processed_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'[OK] Processed: {event.name}')
                    )
                elif result == 'skipped':
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'[SKIP] Skipped: {event.name} (game not final)')
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

    def batch_fetch_game_data(self, events) -> dict[str, dict]:
        """
        Batch fetch game data for multiple events to minimize API calls.
        
        Args:
            events: QuerySet or list of PredictionEvents to fetch data for
            
        Returns:
            Dictionary mapping nba_game_id to game data dict
        """
        game_data_map = {}
        
        # Collect unique game IDs, dates, and team tricodes from events
        unique_game_ids = set()
        dates = set()
        team_tricodes = set()
        
        for event in events:
            game = event.scheduled_game
            game_id = game.nba_game_id
            unique_game_ids.add(game_id)
            
            # Extract date from game_date
            if hasattr(game, 'game_date') and game.game_date:
                date_str = game.game_date.strftime('%Y-%m-%d')
                dates.add(date_str)
            
            # Collect team tricodes
            if hasattr(game, 'home_team_tricode') and game.home_team_tricode:
                team_tricodes.add(game.home_team_tricode)
            if hasattr(game, 'away_team_tricode') and game.away_team_tricode:
                team_tricodes.add(game.away_team_tricode)
        
        if not unique_game_ids:
            return game_data_map
        
        # Add the next day to each date to handle timezone differences
        # Games stored in GMT might be on the next day in US local time (EST/PST)
        extended_dates = set(dates)
        for date_str in dates:
            try:
                # Parse the date string and add one day
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                next_date = date_obj + timedelta(days=1)
                next_date_str = next_date.strftime('%Y-%m-%d')
                extended_dates.add(next_date_str)
            except (ValueError, TypeError) as e:
                logger.warning(f'Failed to add next day for date {date_str}: {e}')
                continue
        
        dates = extended_dates
        
        self.stdout.write(f'Fetching data for {len(unique_game_ids)} unique games...')
        
        # Look up BallDontLie team IDs from team tricodes
        team_ids = []
        if team_tricodes:
            for tricode in team_tricodes:
                team_option = NbaTeamManager.get_by_abbreviation(tricode)
                if team_option and team_option.external_id:
                    try:
                        team_id = int(team_option.external_id)
                        if team_id not in team_ids:
                            team_ids.append(team_id)
                    except (ValueError, TypeError):
                        logger.warning(f'Invalid external_id for team {tricode}: {team_option.external_id}')
                        continue
        
        try:
            client = _build_bdl_client()
            if client is None:
                self.stdout.write(self.style.WARNING('BallDontLie API client not available'))
                return game_data_map
            
            # Single API call with all dates and team IDs
            if dates:
                date_list = list(dates)
                self.stdout.write(f'Filtering by dates: {sorted(date_list)}')
                if team_ids:
                    self.stdout.write(f'Filtering by team IDs: {sorted(team_ids)}')
                
                try:
                    # Build API call parameters
                    api_params = {
                        'per_page': 100,
                        'dates': date_list
                    }
                    
                    # Add team_ids if we have them
                    if team_ids:
                        api_params['team_ids'] = team_ids
                    
                    # Use per_page=100 (maximum allowed) to get all games in one call
                    response = client.nba.games.list(**api_params)
                    
                    # Process the response to extract game data
                    games_found = 0
                    for game in getattr(response, "data", []) or []:
                        game_id = str(getattr(game, "id", ""))
                        if game_id in unique_game_ids:
                            game_data_map[game_id] = self._extract_game_data_from_response(game)
                            games_found += 1
                    
                    self.stdout.write(f'Found data for {games_found} games in batch fetch')
                    
                    # Check if we need to handle pagination
                    meta = getattr(response, "meta", None)
                    next_cursor = getattr(meta, "next_cursor", None) if meta else None
                    
                    # If there's a next cursor and we're missing some games, fetch next page
                    while next_cursor is not None:
                        missing_games = unique_game_ids - set(game_data_map.keys())
                        if not missing_games:
                            break  # We have all the games we need
                        
                        try:
                            # Build API call parameters for pagination
                            api_params = {
                                'per_page': 100,
                                'dates': date_list,
                                'cursor': next_cursor
                            }
                            
                            # Add team_ids if we have them
                            if team_ids:
                                api_params['team_ids'] = team_ids
                            
                            response = client.nba.games.list(**api_params)
                            
                            for game in getattr(response, "data", []) or []:
                                game_id = str(getattr(game, "id", ""))
                                if game_id in unique_game_ids:
                                    game_data_map[game_id] = self._extract_game_data_from_response(game)
                                    games_found += 1
                            
                            meta = getattr(response, "meta", None)
                            next_cursor = getattr(meta, "next_cursor", None) if meta else None
                        except Exception as e:
                            logger.warning(f'Failed to fetch next page with cursor {next_cursor}: {e}')
                            break
                        
                except Exception as e:
                    logger.warning(f'Failed to batch fetch games for dates {date_list}: {e}')
                    self.stdout.write(self.style.WARNING(f'Batch fetch failed: {e}'))
            
            # Fallback: if we still don't have all games, fetch missing ones individually
            missing_games = unique_game_ids - set(game_data_map.keys())
            if missing_games:
                self.stdout.write(f'Fetching {len(missing_games)} remaining games individually...')
                for game_id in missing_games:
                    try:
                        response = client.nba.games.get(int(game_id))
                        game = getattr(response, "data", None)
                        if game:
                            game_data_map[game_id] = self._extract_game_data_from_response(game)
                    except Exception as e:
                        logger.warning(f'Failed to fetch data for game {game_id}: {e}')
                        continue
                        
        except Exception as e:
            logger.exception(f'Failed to batch fetch game data: {e}')
            self.stdout.write(self.style.ERROR(f'Failed to fetch game data: {e}'))
        
        return game_data_map

    def _extract_game_data_from_response(self, game) -> dict:
        """
        Extract game data from BallDontLie API response.
        
        Args:
            game: Game object from BallDontLie API
            
        Returns:
            Dictionary with game data in the same format as get_live_game_data
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

    def process_single_game(self, event: PredictionEvent, game_data: dict, dry_run: bool = False) -> Optional[str]:
        """
        Process a single game and create EventOutcome if game is final.
        
        Args:
            event: PredictionEvent to process
            game_data: Dictionary with game data (from batch fetch)
            dry_run: If True, don't actually create outcomes
        
        Returns:
            'processed' if outcome was created
            'skipped' if game is not final or no valid outcome
            None if there was an error
        """
        game = event.scheduled_game
        
        # Get status and check if game is final
        game_status = game_data.get('game_status', '')
        status_lower = game_status.lower()
        if 'final' not in status_lower:
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
            # Store game result data in metadata
            game_result_metadata = {
                'away_score': away_score,
                'home_score': home_score,
                'away_team': game.away_team_tricode,
                'home_team': game.home_team_tricode,
                'away_team_full': game.away_team,
                'home_team_full': game.home_team,
                'game_status': game_status,  # Store original status, not lowercased
                'nba_game_id': game.nba_game_id,
            }
            
            outcome = EventOutcome.objects.create(
                prediction_event=event,
                winning_option=winning_option,
                winning_generic_option=winning_option.option,
                resolved_at=timezone.now(),
                metadata=game_result_metadata,
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
