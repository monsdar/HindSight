import logging
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from django.utils import timezone
from .models import (
    PredictionEvent,
    TipType,
)


logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Base summary of a BallDontLie synchronisation run."""

    created: int = 0
    updated: int = 0
    removed: int = 0

    @property
    def changed(self) -> bool:
        """Return ``True`` when the sync modified the database."""

        return any((self.created, self.updated, self.removed))




def sync_weekly_games_via_source(limit: int = 7) -> Tuple[Optional[TipType], List[PredictionEvent], Optional[date]]:
    """
    Sync weekly games using the NBA event source.
    
    This is the recommended way to sync games using the event source system.
    """
    from .event_sources import get_source
    
    try:
        nba_source = get_source('nba-balldontlie')
        if nba_source.is_configured():
            nba_source.sync_options()  # Sync teams/players first
            nba_source.sync_events(limit=limit)  # Then sync events
    except Exception:
        logger.exception("Failed to sync via NBA event source")
    
    # Return current state
    tip_type = TipType.objects.filter(slug='weekly-games').first()
    if not tip_type:
        return None, [], None
    
    events = list(
        PredictionEvent.objects.filter(
            tip_type=tip_type,
            is_active=True,
        ).order_by('deadline', 'sort_order')
    )
    
    week_start = None
    if events:
        earliest = events[0].deadline
        week_start = timezone.localdate(earliest)
        if tip_type.deadline != earliest:
            TipType.objects.filter(pk=tip_type.pk).update(deadline=earliest)
            tip_type.deadline = earliest
    
    return tip_type, events, week_start
