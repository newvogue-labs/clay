"""D-12d D5: Wire FATAL→halt (broad-halt).

Connects ``ReconcileReport.has_fatal`` (including age-escalation from D3)
to the durable halt-latch (D4). When a fatal mismatch is detected:

1. Engage the halt-latch → SessionMode.HALTED
2. Place denied globally (cancel/reduce allowed — ADR-033 §4)
3. Narrow per-symbol — NOT now (future slice)

Dormant by default (``CLAY_ORDER_LEDGER_ENABLED``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from clay.execution.ledger.halt_latch import HaltLatchRepository
from clay.execution.ledger.reconcile import ReconcileReport

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker


logger = logging.getLogger(__name__)


class FatalHaltWiring:
    """Wires FATAL reconcile reports to the durable halt-latch.

    When a reconcile tick produces ``has_fatal=True`` (ILLEGAL_DRIFT,
    VENUE_ORPHAN, or age-escalated UNKNOWN), the halt-latch is engaged
    and the execution gate enters HALTED mode.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker,  # type: ignore[type-arg]
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now_fn = now_fn or (lambda: datetime.now(UTC))

    def on_fatal_report(
        self,
        report: ReconcileReport,
        *,
        venue: str,
        symbol: str,
    ) -> bool:
        """Process a reconcile report with fatal mismatches.

        Engages the halt-latch if ``report.has_fatal`` is True.
        Returns True if the latch was engaged, False otherwise.
        """
        if not report.has_fatal:
            return False

        now = self._now_fn()
        reason = self._build_reason(report, venue, symbol)

        with self._session_factory() as s:
            repo = HaltLatchRepository(s)
            repo.engage(reason=reason, now=now)
            s.commit()

        logger.warning(
            "fatal_halt: latch engaged for %s/%s — reason: %s",
            venue,
            symbol,
            reason,
        )
        return True

    def on_escalated_fatal(
        self,
        *,
        venue: str,
        symbol: str,
        escalated_cids: list[str],
    ) -> bool:
        """Process age-escalated UNKNOWNs as fatal.

        Called by the unknown-resolver when projections exceed
        ``unknown_escalation_seconds``.
        """
        if not escalated_cids:
            return False

        now = self._now_fn()
        reason = (
            f"age_escalation: {len(escalated_cids)} UNKNOWN projections "
            f"exceeded escalation threshold (venue={venue}, symbol={symbol})"
        )

        with self._session_factory() as s:
            repo = HaltLatchRepository(s)
            repo.engage(reason=reason, now=now)
            s.commit()

        logger.warning(
            "fatal_halt: latch engaged for %s/%s — age escalation (%d cids)",
            venue,
            symbol,
            len(escalated_cids),
        )
        return True

    def _build_reason(
        self,
        report: ReconcileReport,
        venue: str,
        symbol: str,
    ) -> str:
        """Build a human-readable reason for the halt-latch."""
        fatal_kinds = set()
        for m in report.mismatches:
            if m.kind.value in {"illegal_drift", "venue_orphan"}:
                fatal_kinds.add(m.kind.value)

        return (
            f"fatal_mismatch: {', '.join(sorted(fatal_kinds))} "
            f"(venue={venue}, symbol={symbol}, "
            f"total_mismatches={len(report.mismatches)})"
        )
