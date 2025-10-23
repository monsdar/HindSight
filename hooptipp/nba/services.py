"""NBA-specific services for syncing teams, players, and games."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional, List, Dict

from balldontlie.exceptions import BallDontLieException
from django.utils import timezone

from hooptipp.predictions.models import Option, OptionCategory

from .client import CachedBallDontLieAPI, build_cached_bdl_client
from .managers import NbaPlayerManager, NbaTeamManager

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Summary of a synchronization run."""

    created: int = 0
    updated: int = 0
    removed: int = 0

    @property
    def changed(self) -> bool:
        """Return True when the sync modified the database."""
        return any((self.created, self.updated, self.removed))


# The BallDontLie free tier allows 5 requests per minute. A throttle of 12.5
# seconds leaves a small safety margin between requests.
PLAYER_SYNC_THROTTLE_SECONDS = 12.5

_BDL_CLIENT_CACHE: dict[str, CachedBallDontLieAPI] = {}
_BDL_CLIENT_LOCK = threading.Lock()

# Mapping from BallDontLie team IDs to NBA team IDs for logo URLs
# This mapping is based on the official NBA team IDs used in their CDN
BALLDONTLIE_TO_NBA_TEAM_ID_MAP = {
    1: 1610612737,   # Atlanta Hawks
    2: 1610612738,   # Boston Celtics
    3: 1610612751,   # Brooklyn Nets
    4: 1610612766,   # Charlotte Hornets
    5: 1610612741,   # Chicago Bulls
    6: 1610612739,   # Cleveland Cavaliers
    7: 1610612742,   # Dallas Mavericks
    8: 1610612743,   # Denver Nuggets
    9: 1610612765,   # Detroit Pistons
    10: 1610612744,  # Golden State Warriors
    11: 1610612745,  # Houston Rockets
    12: 1610612754,  # Indiana Pacers
    13: 1610612746,  # LA Clippers
    14: 1610612747,  # Los Angeles Lakers
    15: 1610612763,  # Memphis Grizzlies
    16: 1610612748,  # Miami Heat
    17: 1610612749,  # Milwaukee Bucks
    18: 1610612750,  # Minnesota Timberwolves
    19: 1610612740,  # New Orleans Pelicans
    20: 1610612752,  # New York Knicks
    21: 1610612760,  # Oklahoma City Thunder
    22: 1610612753,  # Orlando Magic
    23: 1610612755,  # Philadelphia 76ers
    24: 1610612756,  # Phoenix Suns
    25: 1610612757,  # Portland Trail Blazers
    26: 1610612758,  # Sacramento Kings
    27: 1610612759,  # San Antonio Spurs
    28: 1610612761,  # Toronto Raptors
    29: 1610612762,  # Utah Jazz
    30: 1610612764,  # Washington Wizards
}


def _get_bdl_api_key() -> str:
    """Return the configured BallDontLie API token formatted for requests."""

    def _candidates():
        yield os.environ.get("BALLDONTLIE_API_TOKEN", "")
        yield os.environ.get("BALLDONTLIE_API_KEY", "")

    for raw_value in _candidates():
        token = raw_value.strip()
        if not token:
            continue

        lower_token = token.lower()
        if lower_token.startswith("bearer "):
            return token

        # Some deployments configure the environment variable with the full
        # header value, e.g. ``Token <key>``. Treat any value that already
        # contains whitespace as a complete header and return it unchanged so
        # we do not accidentally prepend an additional prefix.
        if " " in token:
            return token

        return f"Bearer {token}"
    return ""


def _build_bdl_client() -> Optional[CachedBallDontLieAPI]:
    api_key = _get_bdl_api_key()
    if not api_key:
        logger.warning(
            "BALLDONTLIE_API_TOKEN environment variable is not configured; "
            "skipping BallDontLie sync."
        )
        return None
    with _BDL_CLIENT_LOCK:
        cached_client = _BDL_CLIENT_CACHE.get(api_key)
        if cached_client is not None:
            return cached_client

        client = build_cached_bdl_client(api_key=api_key)
        _BDL_CLIENT_CACHE[api_key] = client
        return client


def sync_teams() -> SyncResult:
    """Fetch the list of NBA teams from BallDontLie and persist them as Options."""
    client = _build_bdl_client()
    if client is None:
        return SyncResult()

    def _list_teams(per_page_value: Optional[int]) -> Any:
        kwargs = {}
        if per_page_value is not None:
            kwargs["per_page"] = per_page_value
        return client.nba.teams.list(**kwargs)

    try:
        response = _list_teams(100)
    except TypeError as exc:
        if "per_page" not in str(exc):
            raise
        logger.debug(
            "NBATeamsAPI.list does not accept per_page parameter; retrying without pagination. %s",
            exc,
        )
        try:
            response = _list_teams(None)
        except BallDontLieException:
            logger.exception("Unable to fetch team list from BallDontLie API.")
            return SyncResult()
    except BallDontLieException:
        logger.exception("Unable to fetch team list from BallDontLie API.")
        return SyncResult()

    created = 0
    updated = 0
    seen_ids: set[str] = set()

    teams_cat = NbaTeamManager.get_category()

    for team in getattr(response, "data", []) or []:
        team_id = getattr(team, "id", None)
        if not team_id:
            continue

        full_name = getattr(team, "full_name", "") or getattr(team, "name", "")
        abbreviation = getattr(team, "abbreviation", "") or ""
        city = getattr(team, "city", "") or ""
        conference = getattr(team, "conference", "") or ""
        division = getattr(team, "division", "") or ""

        if not (conference and division):
            continue

        name = full_name or city or abbreviation
        if not name:
            continue

        # Map BallDontLie team ID to NBA team ID for logo URLs
        nba_team_id = BALLDONTLIE_TO_NBA_TEAM_ID_MAP.get(team_id, team_id)
        
        defaults = {
            "slug": abbreviation.lower() if abbreviation else name.lower().replace(" ", "-"),
            "name": name,
            "short_name": abbreviation,
            "description": f"{city} - {conference} Conference" if conference else city,
            "metadata": {
                "city": city,
                "conference": conference,
                "division": division,
                "nba_team_id": nba_team_id,  # Store NBA team ID for logo URLs
                "balldontlie_team_id": team_id,  # Store original BallDontLie ID for reference
            },
            "is_active": True,
            "sort_order": 0,
        }

        external_id = str(team_id)
        option, created_flag = Option.objects.update_or_create(
            category=teams_cat,
            external_id=external_id,
            defaults=defaults,
        )

        seen_ids.add(external_id)
        if created_flag:
            created += 1
        else:
            updated += 1

    # Remove teams that no longer exist
    removed = 0
    if seen_ids:
        query = Option.objects.filter(category=teams_cat)
        query = query.exclude(external_id__in=seen_ids)
        removed, _ = query.delete()

    return SyncResult(created=created, updated=updated, removed=removed)


def sync_players(throttle_seconds: float = PLAYER_SYNC_THROTTLE_SECONDS) -> SyncResult:
    """
    Fetch all NBA players from BallDontLie and persist them as Options.

    The API is rate limited to five requests per minute. ``throttle_seconds``
    governs the sleep interval between subsequent requests to stay within that
    budget.
    """
    client = _build_bdl_client()
    if client is None:
        return SyncResult()

    seen_ids: set[str] = set()
    created = 0
    updated = 0
    processed = 0

    cursor: Optional[int] = None
    seen_cursors: set[Optional[int]] = set()

    players_cat = NbaPlayerManager.get_category()

    while True:
        params: dict[str, Any] = {"per_page": 100}
        if cursor is not None:
            params["cursor"] = cursor

        try:
            response = client.nba.players.list(**params)
        except BallDontLieException:
            logger.exception("Unable to fetch player list from BallDontLie API.")
            break

        for player in getattr(response, "data", []) or []:
            player_id = getattr(player, "id", None)
            if player_id is None:
                continue

            first_name = getattr(player, "first_name", "") or ""
            last_name = getattr(player, "last_name", "") or ""
            if not (first_name or last_name):
                continue

            display_name = f"{first_name} {last_name}".strip()
            position = getattr(player, "position", "") or ""

            team_obj = getattr(player, "team", None)
            team_abbr = getattr(team_obj, "abbreviation", "") if team_obj else ""
            team_name = getattr(team_obj, "full_name", "") or getattr(team_obj, "name", "") if team_obj else ""

            short_name = f"{first_name[0]}. {last_name}" if first_name else last_name
            description = f"{position} - {team_abbr}" if team_abbr else position

            # Generate a unique slug by including the player ID to avoid duplicates
            base_slug = f"{first_name}-{last_name}".lower().replace(" ", "-")
            # Remove any special characters that might cause issues
            base_slug = re.sub(r'[^a-z0-9\-]', '', base_slug)
            # Ensure slug is unique by appending player ID
            unique_slug = f"{base_slug}-{player_id}"
            
            defaults = {
                "slug": unique_slug,
                "name": display_name,
                "short_name": short_name,
                "description": description,
                "metadata": {
                    "position": position,
                    "team_abbreviation": team_abbr,
                    "team_name": team_name,
                },
                "is_active": True,
                "sort_order": 0,
            }

            external_id = str(player_id)
            _, created_flag = Option.objects.update_or_create(
                category=players_cat,
                external_id=external_id,
                defaults=defaults,
            )

            if created_flag:
                created += 1
            else:
                updated += 1

            seen_ids.add(external_id)
            processed += 1

        meta = getattr(response, "meta", None)
        next_cursor = _extract_next_cursor(meta)
        if next_cursor is None or next_cursor in seen_cursors:
            break

        seen_cursors.add(next_cursor)
        cursor = next_cursor

        if throttle_seconds > 0:
            time.sleep(throttle_seconds)

    # Remove players that no longer exist
    removed = 0
    if processed:
        query = Option.objects.filter(category=players_cat)
        if seen_ids:
            query = query.exclude(external_id__in=seen_ids)
        removed, _ = query.delete()

    return SyncResult(created=created, updated=updated, removed=removed)


def _extract_next_cursor(meta: Any) -> Optional[int | str]:
    """Extract the next cursor from API response metadata."""
    if meta is None:
        return None

    next_cursor = getattr(meta, "next_cursor", None)
    if next_cursor is not None:
        return next_cursor

    if isinstance(meta, dict):
        if meta.get("next_cursor") is not None:
            return meta["next_cursor"]

        next_link: Optional[Any] = meta.get("next")
        if isinstance(meta.get("links"), dict):
            next_link = next_link or meta["links"].get("next")

        if isinstance(next_link, str) and next_link:
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(next_link)
            query = parse_qs(parsed.query)
            raw_cursor: Optional[str] = None
            for key in ("cursor", "page", "next_cursor"):
                values = query.get(key)
                if values:
                    raw_cursor = values[0]
                    break
            if raw_cursor is not None:
                try:
                    return int(raw_cursor)
                except (TypeError, ValueError):
                    return raw_cursor

        if meta.get("next_page") is not None:
            return meta["next_page"]

    return None

# Card rendering helpers
def get_team_logo_url(team_identifier: str) -> str:
    """
    Get the URL for an NBA team logo.

    Args:
        team_identifier: Team abbreviation (e.g., 'LAL', 'BOS') or NBA team ID

    Returns:
        URL to team logo image
    """
    from django.core.cache import cache
    
    # Check if it's already a numeric NBA team ID
    if team_identifier.isdigit():
        nba_team_id = team_identifier
    else:
        # Look up NBA team ID from abbreviation
        cache_key = f"nba_team_id_{team_identifier}"
        nba_team_id = cache.get(cache_key)
        
        if nba_team_id is None:
            # Query the database for the team
            teams_cat = NbaTeamManager.get_category()
            team_option = Option.objects.filter(
                category=teams_cat,
                short_name__iexact=team_identifier
            ).first()
            
            if team_option and team_option.metadata:
                nba_team_id = team_option.metadata.get("nba_team_id")
                # Cache for 1 hour
                if nba_team_id:
                    cache.set(cache_key, nba_team_id, 3600)
    
    # Fallback to abbreviation if we couldn't find the NBA team ID
    if not nba_team_id:
        nba_team_id = team_identifier
    
    # Using NBA's official CDN for team logos
    return f"https://cdn.nba.com/logos/nba/{nba_team_id}/global/L/logo.svg"


def get_live_game_data(nba_game_id: str) -> dict:
    """
    Fetch live game data (scores, status).

    Cached for 30 seconds to avoid rate limits.

    Args:
        nba_game_id: NBA game identifier

    Returns:
        Dictionary with live game data:
        {
            'away_score': int | None,
            'home_score': int | None,
            'game_status': str,  # e.g., "Q3 5:23", "Final"
            'is_live': bool,
        }
    """
    from django.core.cache import cache

    cache_key = f"nba_live_game_{nba_game_id}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return cached_data

    # Default data structure
    data = {
        "away_score": None,
        "home_score": None,
        "game_status": "",
        "is_live": False,
    }

    try:
        client = _build_bdl_client()
        if client is None:
            return data

        # Fetch game data from BallDontLie
        response = client.nba.games.get(int(nba_game_id))
        
        # The API returns a BaseResponse object with a 'data' attribute
        game = getattr(response, "data", None)
        if game is None:
            logger.warning(f"No game data found for game {nba_game_id}")
            return data

        # Extract scores
        data["home_score"] = getattr(game, "home_team_score", None)
        data["away_score"] = getattr(game, "visitor_team_score", None)

        # Extract status
        status = getattr(game, "status", "")
        data["game_status"] = status

        # Determine if game is live
        status_lower = str(status).lower()
        data["is_live"] = any(
            keyword in status_lower
            for keyword in ["q1", "q2", "q3", "q4", "ot", "halftime"]
        )

        # Cache for 30 seconds
        cache.set(cache_key, data, 30)

    except Exception as e:
        logger.exception(f"Failed to fetch live game data for {nba_game_id}: {e}")

    return data


def get_player_card_data(player_external_id: str) -> dict:
    """
    Get player data for card display.

    Args:
        player_external_id: External player ID (e.g., BallDontLie ID)

    Returns:
        Dictionary with player display data:
        {
            'portrait_url': str | None,
            'team': str,
            'team_tricode': str,
            'position': str,
            'current_stats': dict | None,
        }
    """
    from django.core.cache import cache

    cache_key = f"nba_player_card_{player_external_id}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return cached_data

    # Default data structure
    data = {
        "portrait_url": None,
        "team": "",
        "team_tricode": "",
        "position": "",
        "current_stats": None,
    }

    try:
        # Fetch from Option model
        players_cat = NbaPlayerManager.get_category()
        player_option = Option.objects.filter(
            category=players_cat, external_id=player_external_id
        ).first()

        if player_option:
            metadata = player_option.metadata or {}
            data["team"] = metadata.get("team_name", "")
            data["team_tricode"] = metadata.get("team_abbreviation", "")
            data["position"] = metadata.get("position", "")

            # Portrait URL - could integrate with NBA CDN if they provide player images
            # For now, return None - extensions can provide their own image service
            data["portrait_url"] = None

            # Current stats - would require additional API call or database
            # For now, return None - can be enhanced later
            data["current_stats"] = None

        # Cache for 1 hour
        cache.set(cache_key, data, 3600)

    except Exception as e:
        logger.exception(f"Failed to fetch player card data for {player_external_id}: {e}")

    return data


def get_mvp_standings() -> list:
    """
    Get current MVP race standings.

    Returns:
        List of top MVP candidates with their ratings.
        Each entry is a dict with 'rank', 'player', and 'score' keys.
    """
    # This would fetch from an external API or calculate based on stats
    # For now, return empty list as this requires additional data sources
    # Extensions can implement their own MVP tracking system
    return []


# HoopsHype scraping functionality for player data
def _get_hoopshype_team_urls() -> Dict[str, str]:
    """
    Return mapping of team names to their HoopsHype salary page URLs.
    
    Returns:
        Dict mapping team names to their HoopsHype URLs
    """
    return {
        'Atlanta Hawks': 'https://eu.hoopshype.com/salaries/teams/atlanta-hawks/1/',
        'Boston Celtics': 'https://eu.hoopshype.com/salaries/teams/boston-celtics/2/',
        'Brooklyn Nets': 'https://eu.hoopshype.com/salaries/teams/brooklyn-nets/17/',
        'Charlotte Hornets': 'https://eu.hoopshype.com/salaries/teams/charlotte-hornets/5312/',
        'Chicago Bulls': 'https://eu.hoopshype.com/salaries/teams/chicago-bulls/4/',
        'Cleveland Cavaliers': 'https://eu.hoopshype.com/salaries/teams/cleveland-cavaliers/5/',
        'Dallas Mavericks': 'https://eu.hoopshype.com/salaries/teams/dallas-mavericks/6/',
        'Denver Nuggets': 'https://eu.hoopshype.com/salaries/teams/denver-nuggets/7/',
        'Detroit Pistons': 'https://eu.hoopshype.com/salaries/teams/detroit-pistons/8/',
        'Golden State Warriors': 'https://eu.hoopshype.com/salaries/teams/golden-state-warriors/9/',
        'Houston Rockets': 'https://eu.hoopshype.com/salaries/teams/houston-rockets/10/',
        'Indiana Pacers': 'https://eu.hoopshype.com/salaries/teams/indiana-pacers/11/',
        'LA Clippers': 'https://eu.hoopshype.com/salaries/teams/los-angeles-clippers/12/',
        'Los Angeles Lakers': 'https://eu.hoopshype.com/salaries/teams/los-angeles-lakers/13/',
        'Memphis Grizzlies': 'https://eu.hoopshype.com/salaries/teams/memphis-grizzlies/29/',
        'Miami Heat': 'https://eu.hoopshype.com/salaries/teams/miami-heat/14/',
        'Milwaukee Bucks': 'https://eu.hoopshype.com/salaries/teams/milwaukee-bucks/15/',
        'Minnesota Timberwolves': 'https://eu.hoopshype.com/salaries/teams/minnesota-timberwolves/16/',
        'New Orleans Pelicans': 'https://eu.hoopshype.com/salaries/teams/new-orleans-pelicans/3/',
        'New York Knicks': 'https://eu.hoopshype.com/salaries/teams/new-york-knicks/18/',
        'Oklahoma City Thunder': 'https://eu.hoopshype.com/salaries/teams/oklahoma-city-thunder/25/',
        'Orlando Magic': 'https://eu.hoopshype.com/salaries/teams/orlando-magic/19/',
        'Philadelphia 76ers': 'https://eu.hoopshype.com/salaries/teams/philadelphia-76ers/20/',
        'Phoenix Suns': 'https://eu.hoopshype.com/salaries/teams/phoenix-suns/21/',
        'Portland Trail Blazers': 'https://eu.hoopshype.com/salaries/teams/portland-trail-blazers/22/',
        'Sacramento Kings': 'https://eu.hoopshype.com/salaries/teams/sacramento-kings/23/',
        'San Antonio Spurs': 'https://eu.hoopshype.com/salaries/teams/san-antonio-spurs/24/',
        'Toronto Raptors': 'https://eu.hoopshype.com/salaries/teams/toronto-raptors/28/',
        'Utah Jazz': 'https://eu.hoopshype.com/salaries/teams/utah-jazz/26/',
        'Washington Wizards': 'https://eu.hoopshype.com/salaries/teams/washington-wizards/27/',
    }


def _scrape_team_roster(team_name: str, team_url: str) -> List[Dict[str, Any]]:
    """
    Scrape a single team's roster from HoopsHype.
    
    Args:
        team_name: Name of the team
        team_url: URL to the team's salary page on HoopsHype
    
    Returns:
        List of player dictionaries with name, position, salary, etc.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(team_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        players = []
        
        # Look for the roster table - this selector may need adjustment based on actual HTML
        roster_table = soup.find('table', class_='hh-salaries-ranking-table')
        if not roster_table:
            # Try alternative selectors
            roster_table = soup.find('table')
        
        if roster_table:
            rows = roster_table.find_all('tr')
            for row in rows[1:]:  # Skip header row
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    # Extract player name (in cell 1, cell 0 is just row number)
                    name_cell = cells[1]
                    player_name = name_cell.get_text(strip=True)
                    
                    # Skip if this looks like a header, empty row, or team total
                    if (not player_name or 
                        player_name.lower() in ['player', 'name', ''] or
                        player_name.startswith('$') or  # Skip salary amounts
                        cells[0].get_text(strip=True).lower() == 'total'):  # Skip total rows
                        continue
                    
                    # Extract current season salary (cell 2 is 2025-26 salary)
                    salary = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                    
                    # For position, we'll need to get it from the player's individual page
                    # or use a default since HoopsHype salary pages don't show position
                    position = ''  # Will be filled from other sources or left empty
                    
                    # Clean up the data
                    player_name = re.sub(r'\s+', ' ', player_name).strip()
                    salary = re.sub(r'\s+', ' ', salary).strip()
                    
                    if player_name:  # Only add if we have a valid name
                        players.append({
                            'name': player_name,
                            'position': position,
                            'salary': salary,
                            'team': team_name,
                        })
        
        logger.info(f"Scraped {len(players)} players from {team_name}")
        return players
        
    except Exception as e:
        logger.error(f"Failed to scrape team roster from {team_url}: {e}")
        return []


def _parse_player_name(full_name: str) -> tuple[str, str]:
    """
    Parse a full player name into first and last name.
    
    Args:
        full_name: Full player name like "LeBron James" or "D'Angelo Russell"
    
    Returns:
        Tuple of (first_name, last_name)
    """
    name_parts = full_name.strip().split()
    if len(name_parts) >= 2:
        first_name = name_parts[0]
        last_name = ' '.join(name_parts[1:])
    elif len(name_parts) == 1:
        first_name = name_parts[0]
        last_name = ''
    else:
        first_name = ''
        last_name = ''
    
    return first_name, last_name


def sync_players_from_hoopshype() -> SyncResult:
    """
    Scrape all NBA team rosters from HoopsHype and sync to database.
    
    This function scrapes player data from HoopsHype salary pages for all 30 NBA teams.
    It's designed to be run once or twice per season to seed initial player data.
    
    Returns:
        SyncResult with created and updated player counts
    """
    logger.info("Starting HoopsHype player sync...")
    
    team_urls = _get_hoopshype_team_urls()
    players_cat = NbaPlayerManager.get_category()
    created = 0
    updated = 0
    total_players = 0
    
    for team_name, team_url in team_urls.items():
        logger.info(f"Scraping roster for {team_name}")
        
        players = _scrape_team_roster(team_name, team_url)
        total_players += len(players)
        
        for player_data in players:
            try:
                # Parse player name
                first_name, last_name = _parse_player_name(player_data['name'])
                
                if not (first_name or last_name):
                    logger.warning(f"Skipping player with invalid name: {player_data}")
                    continue
                
                # Generate unique slug using team name and full name for better uniqueness
                base_slug = f"{first_name}-{last_name}".lower().replace(" ", "-")
                base_slug = re.sub(r'[^a-z0-9\-]', '', base_slug)
                # Use team name and full name hash for better uniqueness
                team_slug = team_name.lower().replace(" ", "-").replace(".", "")
                team_slug = re.sub(r'[^a-z0-9\-]', '', team_slug)
                unique_slug = f"{base_slug}-{team_slug}-{abs(hash(player_data['name'] + team_name)) % 10000}"
                
                # Create display name and short name
                display_name = f"{first_name} {last_name}".strip()
                short_name = f"{first_name[0]}. {last_name}" if first_name else last_name
                
                # Create description
                description = f"{player_data['position']} - {team_name}" if player_data['position'] else team_name
                
                # Use team name + player name hash as external ID for better uniqueness
                external_id = f"hoopshype-{team_slug}-{abs(hash(player_data['name'] + team_name))}"
                
                defaults = {
                    "slug": unique_slug,
                    "name": display_name,
                    "short_name": short_name,
                    "description": description,
                    "metadata": {
                        "position": player_data['position'],
                        "team": team_name,
                        "salary": player_data['salary'],
                        "source": "hoopshype",
                    },
                    "is_active": True,
                    "sort_order": 0,
                }
                
                _, created_flag = Option.objects.update_or_create(
                    category=players_cat,
                    external_id=external_id,
                    defaults=defaults,
                )
                
                if created_flag:
                    created += 1
                else:
                    updated += 1
                    
            except Exception as e:
                logger.error(f"Failed to process player {player_data}: {e}")
                continue
        
        # Small delay to be respectful to the server
        time.sleep(1)
    
    logger.info(f"HoopsHype sync completed: {created} created, {updated} updated, {total_players} total players processed")
    return SyncResult(created=created, updated=updated, removed=0)
