"""Utility classes for caching BallDontLie API calls."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional, Tuple

from balldontlie import BalldontlieAPI
from django.utils import timezone
from django.utils.dateparse import parse_datetime


@dataclass
class _CacheEntry:
    value: Any
    expires_at: Optional[datetime]

    def is_valid(self) -> bool:
        if self.expires_at is None:
            return True
        return self.expires_at > timezone.now()


def _freeze_params(params: Dict[str, Any]) -> Tuple[Tuple[str, Any], ...]:
    def _freeze(value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
        if isinstance(value, (list, tuple, set)):
            return tuple(_freeze(v) for v in value)
        return value

    return tuple(sorted((key, _freeze(val)) for key, val in params.items()))


class _CachedGamesAPI:
    """Caches expensive BallDontLie NBA games API calls."""

    _IN_PROGRESS_REFRESH = timedelta(minutes=1)

    def __init__(self, games_api: Any) -> None:
        self._games_api = games_api
        self._cache: Dict[Tuple[str, Any], _CacheEntry] = {}
        self._lock = threading.Lock()

    def list(self, **params: Any) -> Any:
        cache_key = ("list", _freeze_params(params))
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        response = self._games_api.list(**params)
        expires_at = self._calculate_list_expiry(getattr(response, "data", []))
        self._set(cache_key, response, expires_at)
        return response

    def get(self, game_id: int) -> Any:
        cache_key = ("get", game_id)
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        response = self._games_api.get(game_id)
        expires_at = self._calculate_game_expiry(getattr(response, "data", None))
        self._set(cache_key, response, expires_at)
        return response

    def _get(self, key: Tuple[str, Any]) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.is_valid():
                return entry.value
            self._cache.pop(key, None)
            return None

    def _set(self, key: Tuple[str, Any], value: Any, expires_at: Optional[datetime]) -> None:
        with self._lock:
            self._cache[key] = _CacheEntry(value=value, expires_at=expires_at)

    def _calculate_list_expiry(self, games: Iterable[Any]) -> Optional[datetime]:
        expiry: Optional[datetime] = None
        for game in games:
            game_expiry = self._calculate_game_expiry(game)
            if game_expiry is None:
                continue
            if expiry is None or game_expiry < expiry:
                expiry = game_expiry
        return expiry

    def _calculate_game_expiry(self, game: Any) -> Optional[datetime]:
        if game is None:
            return timezone.now() + self._IN_PROGRESS_REFRESH

        status = (getattr(game, "status", "") or "").strip().lower()
        if not status:
            return timezone.now() + self._IN_PROGRESS_REFRESH

        if "final" in status or "end" in status:
            return None

        if "schedule" in status or "not started" in status:
            start_time = self._parse_game_time(getattr(game, "date", ""))
            if start_time is None:
                return timezone.now() + self._IN_PROGRESS_REFRESH
            return start_time

        return timezone.now() + self._IN_PROGRESS_REFRESH

    @staticmethod
    def _parse_game_time(raw: str) -> Optional[datetime]:
        if not raw:
            return None
        parsed = parse_datetime(raw)
        if parsed is None:
            # Some responses include milliseconds with a trailing Z
            raw = raw.replace("Z", "+00:00")
            parsed = parse_datetime(raw)
        if parsed is None:
            return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)
        return parsed


class _CachedNbaAPI:
    def __init__(self, nba_api: Any) -> None:
        self._nba_api = nba_api
        self.games = _CachedGamesAPI(nba_api.games)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._nba_api, item)


class CachedBallDontLieAPI:
    """Wraps :class:`BalldontlieAPI` with a small in-memory cache."""

    def __init__(self, api: BalldontlieAPI) -> None:
        self._api = api
        self.nba = _CachedNbaAPI(api.nba)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._api, item)


def build_cached_bdl_client(api_key: str) -> CachedBallDontLieAPI:
    """Return a cached BallDontLie API client."""

    return CachedBallDontLieAPI(BalldontlieAPI(api_key=api_key))
