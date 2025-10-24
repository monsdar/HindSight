"""
Management command to download NBA team logos and store them locally.

This command fetches team logos from the NBA CDN and stores them in the static
directory for local use, eliminating the need to fetch them from external sources.
"""

from __future__ import annotations

import logging
import os
import requests
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.files.storage import default_storage

from hooptipp.nba.managers import NbaTeamManager
from hooptipp.nba.services import BALLDONTLIE_TO_NBA_TEAM_ID_MAP

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Download NBA team logos and store them locally in the static directory'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be downloaded without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force download even if logos already exist locally',
        )
        parser.add_argument(
            '--team',
            type=str,
            help='Download logo for a specific team abbreviation (e.g., LAL, BOS)',
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['svg', 'png'],
            default='svg',
            help='Logo format to download (default: svg)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        team_filter = options['team']
        logo_format = options['format']
        
        # Get static directory
        static_dir = Path(settings.STATICFILES_DIRS[0]) if settings.STATICFILES_DIRS else Path(settings.STATIC_ROOT)
        logos_dir = static_dir / 'nba' / 'logos'
        
        # Create logos directory if it doesn't exist
        if not dry_run:
            logos_dir.mkdir(parents=True, exist_ok=True)
            self.stdout.write(f'Created logos directory: {logos_dir}')
        
        # Get NBA teams
        teams = NbaTeamManager.all()
        
        if team_filter:
            teams = teams.filter(short_name__iexact=team_filter)
            if not teams.exists():
                raise CommandError(f'No team found with abbreviation: {team_filter}')
        
        self.stdout.write(f'Found {teams.count()} NBA teams')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No files will be downloaded'))
        
        downloaded_count = 0
        skipped_count = 0
        error_count = 0
        
        for team in teams:
            try:
                result = self.download_team_logo(team, logos_dir, logo_format, force, dry_run)
                if result == 'downloaded':
                    downloaded_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'[OK] Downloaded: {team.short_name} ({team.name})')
                    )
                elif result == 'skipped':
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'[SKIP] Skipped: {team.short_name} (already exists)')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'[SKIP] Skipped: {team.short_name} (no NBA team ID)')
                    )
                    skipped_count += 1
            except Exception as e:
                error_count += 1
                logger.exception(f'Error downloading logo for {team.short_name}: {e}')
                self.stdout.write(
                    self.style.ERROR(f'[ERROR] Error downloading {team.short_name}: {e}')
                )
        
        # Summary
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed: {downloaded_count} downloaded, {skipped_count} skipped, {error_count} errors'
            )
        )
        
        if not dry_run and downloaded_count > 0:
            self.stdout.write('')
            self.stdout.write(
                self.style.SUCCESS(
                    f'Logos saved to: {logos_dir}'
                )
            )
            self.stdout.write(
                'You can now update the get_team_logo_url function to use local logos instead of CDN URLs.'
            )

    def download_team_logo(self, team, logos_dir: Path, logo_format: str, force: bool, dry_run: bool) -> Optional[str]:
        """
        Download a team logo and save it locally.
        
        Returns:
            'downloaded' if logo was downloaded
            'skipped' if logo already exists and force=False
            None if no NBA team ID available
        """
        # Get NBA team ID from metadata
        nba_team_id = team.metadata.get('nba_team_id')
        if not nba_team_id:
            return None
        
        # Determine file extension and URL format
        if logo_format == 'svg':
            file_extension = 'svg'
            url_path = f"global/L/logo.svg"
        else:  # png
            file_extension = 'png'
            url_path = f"global/L/logo.png"
        
        # Build local file path
        logo_filename = f"{team.short_name.lower()}.{file_extension}"
        local_path = logos_dir / logo_filename
        
        # Check if file already exists
        if not force and local_path.exists():
            return 'skipped'
        
        # Build CDN URL
        cdn_url = f"https://cdn.nba.com/logos/nba/{nba_team_id}/{url_path}"
        
        if dry_run:
            self.stdout.write(f'  Would download: {cdn_url} -> {local_path}')
            return 'downloaded'
        
        # Download the logo
        try:
            response = requests.get(cdn_url, timeout=30)
            response.raise_for_status()
            
            # Save the file
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f'Downloaded logo for {team.short_name}: {local_path}')
            return 'downloaded'
            
        except requests.RequestException as e:
            logger.error(f'Failed to download logo for {team.short_name}: {e}')
            raise CommandError(f'Failed to download logo for {team.short_name}: {e}')
        except IOError as e:
            logger.error(f'Failed to save logo for {team.short_name}: {e}')
            raise CommandError(f'Failed to save logo for {team.short_name}: {e}')
