"""
Logo discovery and matching utility for DBB teams.

Automatically matches team names to logo files in static/dbb/ directory
using substring matching.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """
    Normalize text for matching.
    
    - Converts to lowercase
    - Handles German umlauts (ä->ae, ö->oe, ü->ue, ß->ss)
    - Removes special characters except hyphens and spaces
    - Converts hyphens to spaces for better matching
    - Strips whitespace
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text
    """
    if not text:
        return ""
    
    # Convert to lowercase
    text = text.lower()
    
    # Replace German umlauts
    replacements = {
        'ä': 'ae',
        'ö': 'oe',
        'ü': 'ue',
        'ß': 'ss',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Remove all special characters except hyphens and spaces
    text = re.sub(r'[^a-z0-9\-\s]', '', text)
    
    # Convert hyphens to spaces for better substring matching
    text = text.replace('-', ' ')
    
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def discover_logo_files() -> dict[str, str]:
    """
    Scan static/dbb/ directory for logo files.
    
    Returns:
        Dictionary mapping normalized slugs to original filenames.
        Example: {'bierden-bassen': 'bierden-bassen.svg'}
    """
    logo_map = {}
    
    # Determine the static/dbb directory path
    static_dbb_path = Path(settings.BASE_DIR) / 'static' / 'dbb'
    
    if not static_dbb_path.exists():
        logger.warning(f"Static DBB directory not found: {static_dbb_path}")
        return logo_map
    
    # Scan for logo files
    for file_path in static_dbb_path.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in ['.svg', '.png', '.jpg', '.jpeg']:
            # Extract the base filename without extension
            slug = file_path.stem
            
            # Normalize the slug for matching
            normalized_slug = normalize_text(slug)
            
            # Store mapping from normalized slug to original filename
            logo_map[normalized_slug] = file_path.name
            
            logger.debug(f"Discovered logo: {file_path.name} (slug: {normalized_slug})")
    
    logger.info(f"Discovered {len(logo_map)} logo file(s) in {static_dbb_path}")
    return logo_map


def find_logo_for_team(team_name: str, logo_map: Optional[dict[str, str]] = None) -> str:
    """
    Find the best matching logo for a team name.
    
    Uses substring matching: the logo slug must be a substring of the
    normalized team name. If multiple matches are found, returns the longest match.
    
    Args:
        team_name: Full team name (e.g., "BG Bierden-Bassen Achim")
        logo_map: Optional pre-computed logo map. If None, will discover logos.
        
    Returns:
        Logo filename if found, empty string otherwise
        
    Examples:
        >>> find_logo_for_team("BG Bierden-Bassen Achim")
        'bierden-bassen.svg'
        >>> find_logo_for_team("TV Bremen")
        'tv-bremen.svg'
        >>> find_logo_for_team("Unknown Team")
        ''
    """
    if not team_name:
        return ""
    
    # Discover logos if not provided
    if logo_map is None:
        logo_map = discover_logo_files()
    
    if not logo_map:
        return ""
    
    # Normalize the team name
    normalized_team_name = normalize_text(team_name)
    
    # Find matching logos (where the logo slug is a substring of the team name)
    matches = []
    for slug, filename in logo_map.items():
        if slug and slug in normalized_team_name:
            matches.append((slug, filename))
    
    if not matches:
        logger.debug(f"No logo found for team: {team_name}")
        return ""
    
    # If multiple matches, prefer the longest match (most specific)
    matches.sort(key=lambda x: len(x[0]), reverse=True)
    best_match = matches[0]
    
    logger.debug(f"Found logo for team '{team_name}': {best_match[1]} (matched on '{best_match[0]}')")
    
    return best_match[1]


def get_logo_for_team(team_name: str, manual_logo: str = "") -> str:
    """
    Get logo for a team, preferring manual assignment over auto-discovery.
    
    Args:
        team_name: Full team name
        manual_logo: Manually assigned logo filename (from TrackedTeam.logo)
        
    Returns:
        Logo filename to use
    """
    # Prefer manual assignment if provided
    if manual_logo:
        return manual_logo
    
    # Fall back to auto-discovery
    return find_logo_for_team(team_name)

