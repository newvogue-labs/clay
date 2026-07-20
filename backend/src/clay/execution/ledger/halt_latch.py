"""HaltLatch repository — durable halt-latch for execution-gate (D-12d D4).

SQLite-portable select-then-upsert pattern (singleton row).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from clay.db.models_orders import HaltLatch


class HaltLatchRepository:
    """Data-access layer for the halt-latch singleton.

    Follows the pattern of :class:`OrderLedgerRepository`:
    takes ``Session`` in the constructor, commits on the caller side.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_latch(self) -> HaltLatch | None:
        """Retrieve the singleton halt-latch row (or None if not yet created)."""
        return self.session.execute(
            select(HaltLatch)
        ).scalars().one_or_none()

    def ensure_latch(self) -> HaltLatch:
        """Get or create the singleton halt-latch row.

        SQLite-portable: select-then-insert if missing.
        """
        latch = self.get_latch()
        if latch is not None:
            return latch
        latch = HaltLatch(
            engaged=False,
            reason=None,
            engaged_at=None,
            reset_at=None,
            reset_reason=None,
        )
        self.session.add(latch)
        self.session.flush()
        return latch

    def engage(self, *, reason: str, now: datetime) -> None:
        """Engage the halt-latch (fail-closed).

        Uses CAS-style update (only disengaged → engaged).
        """
        latch = self.ensure_latch()
        if latch.engaged:
            return  # already engaged — idempotent
        latch.engaged = True
        latch.reason = reason
        latch.engaged_at = now
        latch.reset_at = None
        latch.reset_reason = None
        self.session.flush()

    def disengage(self, *, reason: str, now: datetime) -> None:
        """Disengage the halt-latch (manual operator reset only).

        Always writes audit trail (reset_at + reset_reason).
        """
        latch = self.ensure_latch()
        latch.engaged = False
        latch.reset_at = now
        latch.reset_reason = reason
        self.session.flush()

    def is_engaged(self) -> bool:
        """Check if the halt-latch is currently engaged."""
        latch = self.get_latch()
        return latch.engaged if latch is not None else False
