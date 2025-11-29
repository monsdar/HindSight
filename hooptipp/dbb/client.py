"""SLAPI HTTP client for German basketball data."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


def _get_api_token() -> str:
    """Get the SLAPI API token from environment."""
    return os.environ.get('SLAPI_API_TOKEN', '').strip()


class SlapiClient:
    """
    HTTP client for the SLAPI API.
    
    Provides methods to fetch German amateur basketball data.
    """

    def __init__(self, base_url: str = "https://slapi.up.railway.app", api_token: Optional[str] = None):
        """
        Initialize the SLAPI client.
        
        Args:
            base_url: Base URL for the SLAPI API
            api_token: API token for authentication (uses env var if not provided)
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token or _get_api_token()
        self.session = requests.Session()
        
        # Set up authentication header if token is available
        if self.api_token:
            self.session.headers.update({
                'Authorization': f'Bearer {self.api_token}'
            })

    def _make_request(self, endpoint: str, params: Optional[dict] = None) -> dict[str, Any]:
        """
        Make a GET request to the SLAPI API.
        
        Args:
            endpoint: API endpoint (e.g., '/verbaende')
            params: Query parameters
            
        Returns:
            JSON response as dictionary
            
        Raises:
            requests.RequestException: If the request fails
        """
        url = urljoin(self.base_url, endpoint)
        
        try:
            response = self.session.get(url, params=params, timeout=90)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"SLAPI request failed for {endpoint}: {e}")
            raise

    def _normalize_list_response(self, response: Any, key: str) -> list[dict[str, Any]]:
        """
        Normalize API responses that should be lists.
        
        Handles both direct list responses and wrapped responses like {"key": [...]}.
        
        Args:
            response: The API response
            key: The key name to look for if response is a dict
            
        Returns:
            List of dictionaries
        """
        if isinstance(response, dict):
            # If response is a dict, try to extract the list
            if key in response:
                return response[key]
            elif 'data' in response:
                return response['data']
            else:
                # If it's a dict but doesn't have expected keys, log and return empty
                logger.warning(f"Unexpected {key} response structure: {response}")
                return []
        elif isinstance(response, list):
            # Direct list response
            return response
        else:
            logger.error(f"Invalid {key} response type: {type(response)}")
            return []

    def get_verbaende(self) -> list[dict[str, Any]]:
        """
        Fetch list of Verbände.
        
        Returns:
            List of Verband dictionaries
        """
        response = self._make_request('/verbaende')
        return self._normalize_list_response(response, 'verbaende')

    def get_club_leagues(self, verband_id: str, club_search: str) -> list[dict[str, Any]]:
        """
        Get leagues that a club participates in by searching within a Verband.
        
        Args:
            verband_id: Verband identifier
            club_search: Club search term (e.g., 'Bierden-Bassen')
            
        Returns:
            List of league dictionaries with club information
        """
        response = self._make_request(
            f'/clubs/{club_search}/leagues',
            params={'verband_id': verband_id}
        )
        
        # Response structure: {"club_name": "...", "verband_id": ..., "leagues": [...]}
        if isinstance(response, dict) and 'leagues' in response:
            return response['leagues']
        elif isinstance(response, list):
            return response
        else:
            logger.warning(f"Unexpected club leagues response structure: {response}")
            return []

    def get_league_standings(self, league_id: str) -> list[dict[str, Any]]:
        """
        Get standings for a league (includes list of teams).
        
        Args:
            league_id: League identifier
            
        Returns:
            List of team standings where team is an object: {"position": 1, "team": {"id": "...", "name": "..."}, ...}
        """
        response = self._make_request(f'/leagues/{league_id}/standings')
        
        # Response structure: {"league_id": "...", "standings": [...]}
        if isinstance(response, dict) and 'standings' in response:
            return response['standings']
        elif isinstance(response, list):
            return response
        else:
            logger.warning(f"Unexpected standings response structure: {response}")
            return []

    def get_league_matches(self, league_id: str) -> list[dict[str, Any]]:
        """
        Get matches for a league.
        
        Args:
            league_id: League identifier
            
        Returns:
            List of match dictionaries where home_team/away_team are objects: {"match_id": 1, "home_team": {"name": "..."}, ...}
        """
        response = self._make_request(f'/leagues/{league_id}/matches')
        
        # Response structure: {"league_id": "...", "matches": [...]}
        if isinstance(response, dict) and 'matches' in response:
            return response['matches']
        elif isinstance(response, list):
            return response
        else:
            logger.warning(f"Unexpected matches response structure: {response}")
            return []

    def get_match_details(self, match_id: str) -> dict[str, Any]:
        """
        Get detailed information for a specific match including location.
        
        Args:
            match_id: Match identifier
            
        Returns:
            Match details dictionary with location information
        """
        return self._make_request(f'/match/{match_id}')


def build_slapi_client() -> Optional[SlapiClient]:
    """
    Build a SLAPI client instance.
    
    Returns:
        SlapiClient instance if token is available, None otherwise
    """
    api_token = _get_api_token()
    if not api_token:
        logger.warning("SLAPI_API_TOKEN not set")
        return None
    
    return SlapiClient(api_token=api_token)

