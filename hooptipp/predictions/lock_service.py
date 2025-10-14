"""Lock management helpers for prediction tips."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Set

from django.utils import timezone

from .models import UserTip


LOCK_LIMIT = 3
LOCK_RETURN_DELAY = timedelta(days=30)


class LockLimitError(Exception):
    """Raised when attempting to lock more predictions than allowed."""


@dataclass(frozen=True)
class LockSummary:
    """Snapshot of a user's lock state."""

    total: int
    available: int
    active: int
    pending: int
    next_return_at: Optional[datetime]


class LockService:
    """Coordinate prediction lock allocation for a user."""

    def __init__(self, user) -> None:
        self.user = user
        self.total = LOCK_LIMIT
        self.available = 0
        self._active_ids: Set[int] = set()
        self._pending_ids: Set[int] = set()
        self._next_return_at: Optional[datetime] = None
        self._initialised = False

    def refresh(self) -> LockSummary:
        """Synchronise lock state and return a summary."""

        now = timezone.now()
        expired_ids = list(
            UserTip.objects.filter(
                user=self.user,
                lock_status=UserTip.LockStatus.FORFEITED,
                lock_releases_at__isnull=False,
                lock_releases_at__lte=now,
            ).values_list("id", flat=True)
        )
        if expired_ids:
            UserTip.objects.filter(id__in=expired_ids).update(
                lock_status=UserTip.LockStatus.RETURNED,
                lock_released_at=now,
                lock_releases_at=None,
            )

        active_ids = set(
            UserTip.objects.filter(user=self.user, is_locked=True).values_list("id", flat=True)
        )
        pending_ids = set(
            UserTip.objects.filter(
                user=self.user,
                lock_status=UserTip.LockStatus.FORFEITED,
                lock_releases_at__gt=now,
            ).values_list("id", flat=True)
        )
        self.available = max(0, self.total - len(active_ids) - len(pending_ids))
        self._active_ids = active_ids
        self._pending_ids = pending_ids
        self._next_return_at = (
            UserTip.objects.filter(
                user=self.user,
                lock_status=UserTip.LockStatus.FORFEITED,
                lock_releases_at__gt=now,
            )
            .order_by("lock_releases_at")
            .values_list("lock_releases_at", flat=True)
            .first()
        )
        self._initialised = True
        return LockSummary(
            total=self.total,
            available=self.available,
            active=len(self._active_ids),
            pending=len(self._pending_ids),
            next_return_at=self._next_return_at,
        )

    def get_summary(self) -> LockSummary:
        """Return a summary without triggering additional queries when possible."""

        if not self._initialised:
            return self.refresh()
        return LockSummary(
            total=self.total,
            available=self.available,
            active=len(self._active_ids),
            pending=len(self._pending_ids),
            next_return_at=self._next_return_at,
        )

    def ensure_locked(self, tip: UserTip) -> bool:
        """Ensure ``tip`` is marked as locked if capacity allows.

        Returns ``True`` when a new lock was allocated.
        """

        if not self._initialised:
            self.refresh()

        if tip.id in self._active_ids or tip.is_locked:
            return False

        if self.available <= 0:
            raise LockLimitError("No locks available")

        now = timezone.now()
        tip.is_locked = True
        tip.lock_status = UserTip.LockStatus.ACTIVE
        tip.lock_committed_at = now
        tip.lock_released_at = None
        tip.lock_releases_at = None
        tip.save(
            update_fields=[
                "is_locked",
                "lock_status",
                "lock_committed_at",
                "lock_released_at",
                "lock_releases_at",
            ]
        )
        self._active_ids.add(tip.id)
        self.available = max(0, self.available - 1)
        return True

    def release_lock(self, tip: UserTip) -> bool:
        """Return a lock associated with ``tip`` immediately."""

        if not self._initialised:
            self.refresh()

        if tip.id not in self._active_ids and not tip.is_locked:
            return False

        now = timezone.now()
        tip.is_locked = False
        tip.lock_status = UserTip.LockStatus.RETURNED
        tip.lock_released_at = now
        tip.lock_releases_at = None
        tip.save(
            update_fields=[
                "is_locked",
                "lock_status",
                "lock_released_at",
                "lock_releases_at",
            ]
        )
        if tip.id in self._active_ids:
            self._active_ids.remove(tip.id)
        self.available = min(self.total, self.available + 1)
        return True

    def schedule_forfeit(self, tip: UserTip, *, resolved_at: datetime) -> None:
        """Mark a lock as forfeited and schedule its automatic return."""

        if not self._initialised:
            self.refresh()

        release_at = resolved_at + LOCK_RETURN_DELAY
        tip.is_locked = False
        tip.lock_status = UserTip.LockStatus.FORFEITED
        tip.lock_releases_at = release_at
        tip.lock_released_at = None
        tip.save(
            update_fields=[
                "is_locked",
                "lock_status",
                "lock_releases_at",
                "lock_released_at",
            ]
        )
        if tip.id in self._active_ids:
            self._active_ids.remove(tip.id)
            self.available = min(self.total, self.available + 1)
        self._pending_ids.add(tip.id)
        if self._next_return_at is None or release_at < self._next_return_at:
            self._next_return_at = release_at

