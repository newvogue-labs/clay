"""D-12c: Periodic reconcile cycle job for ClayScheduler.

Async coroutine registered with ``ClayScheduler._arun_safely``.
Iterates active order projections, reconciles each ``(venue, symbol)``
pair against venue truth, and emits ``reconcile.cycle`` events on
state transitions. Fatal mismatches engage the durable halt-latch
via ``FatalHaltWiring`` (D-15) when wired.

Dormant by default (``CLAY_SCHEDULER_RECONCILE_ENABLED=false``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from clay.execution.ledger.reconcile import OrderReconcileService
from clay.execution.ledger.repository import OrderLedgerRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from clay.audit.writer import AuditWriter
    from clay.events.bus import EventBus
    from clay.execution.ledger.fatal_halt import FatalHaltWiring

logger = logging.getLogger(__name__)


class OrderReconcileJob:
    """D-12c scheduler-driven reconcile cycle — async coroutine for the event loop.

    Each tick:

    1. Opens a transient ``Session``, reads distinct ``(venue, symbol)``
       pairs from active projections via ``list_active_projections()``.
    2. For each pair, calls ``reconcile_service.reconcile_symbol()``
       with the configured ``lookback_seconds`` window.
    3. Aggregates all ``ReconcileReport`` instances into a cycle-level
       summary ``(any_fatal, total_mismatches)``.
    4. Anti-flood: first run seeds ``_cache`` and returns (no emit).
       Steady state (same tuple) → return. Transition → emit
       ``reconcile.cycle`` audit + bus, update ``_cache``.
    5. Fatal report (``has_fatal``) → audit ``reconcile.fatal_mismatch``
       (signal-only, no halt/pause).

    Error policy (isolated from ``HealthTickJob``, B4/B5 pattern):

    ``on_error`` is invoked by ``ClayScheduler._arun_safely`` on a tick
    exception. Writes ``reconcile.cycle_failed`` **once per failing
    episode** (anti-flood). Sets ``_failing = True``; reset on next
    successful ``run()`` (Acceptance #11).
    """

    def __init__(
        self,
        *,
        reconcile_service: OrderReconcileService,
        session_factory: sessionmaker,  # type: ignore[type-arg]
        audit_writer: AuditWriter,
        event_bus: EventBus,
        lookback_seconds: int = 3600,
        now_fn: Callable[[], datetime] | None = None,
        fatal_halt_wiring: FatalHaltWiring | None = None,
    ) -> None:
        self._reconcile_service = reconcile_service
        self._session_factory = session_factory
        self._audit_writer = audit_writer
        self._event_bus = event_bus
        self._lookback_seconds = lookback_seconds
        self._now_fn = now_fn or (lambda: datetime.now(UTC))
        self._fatal_halt_wiring = fatal_halt_wiring
        # Anti-flood: (any_fatal, total_mismatches). First-run seed.
        self._cache: tuple[bool, int] | None = None
        # Episode flag for on_error anti-flood; reset on success.
        self._failing: bool = False
        # D-12d D8: transition-gated fatal audit (write on transition, not every tick)
        self._was_fatal: bool = False

    async def run(self) -> None:
        """Execute one reconcile-cycle tick. See class docstring."""
        # Step 1: read active (venue, symbol) pairs.
        with self._session_factory() as session:
            repo = OrderLedgerRepository(session)
            active = repo.list_active_projections()

        # Deduplicate to distinct (venue, symbol) pairs.
        pairs: set[tuple[str, str]] = set()
        for p in active:
            if p.venue and p.symbol:
                pairs.add((p.venue, p.symbol))

        if not pairs:
            # No active projections — seed or no-op.
            if self._cache is None:
                self._cache = (False, 0)
            # B4 #11: successful tick closes failing episode.
            self._failing = False
            return

        # Step 2: reconcile each pair.
        since = self._now_fn() - timedelta(seconds=self._lookback_seconds)
        any_fatal = False
        total_mismatches = 0

        for venue, symbol in sorted(pairs):
            try:
                report = await self._reconcile_service.reconcile_symbol(
                    symbol, since, venue=venue
                )
                total_mismatches += len(report.mismatches)
                if report.has_fatal:
                    any_fatal = True
                    # D-15: engage halt-latch when wiring is bound
                    if self._fatal_halt_wiring is not None:
                        self._fatal_halt_wiring.on_fatal_report(
                            report, venue=venue, symbol=symbol
                        )
            except Exception:
                logger.exception(
                    "clay.scheduler: reconcile_symbol failed for %s/%s",
                    venue,
                    symbol,
                )
                raise

        # D-12d D8: transition-gated fatal audit (write on transition, not every tick)
        if any_fatal and not self._was_fatal:
            # Transition: non-fatal → fatal — write audit ONCE per transition
            self._audit_writer.write(
                "reconcile.fatal_mismatch",
                {
                    "any_fatal": True,
                    "total_mismatches": total_mismatches,
                    "pairs_reconciled": len(pairs),
                },
            )
        elif not any_fatal and self._was_fatal:
            # Transition: fatal → non-fatal — log recovery
            logger.info(
                "reconcile: fatal mismatch cleared after %d ticks",
                total_mismatches,
            )
        self._was_fatal = any_fatal

        # Step 4: anti-flood transition diff.
        # B4 #11: a successful tick closes the failing episode so a
        # later failure re-emits ``reconcile.cycle_failed``.
        self._failing = False
        new_state = (any_fatal, total_mismatches)
        if self._cache is None:
            # First run — seed, do not emit.
            self._cache = new_state
            return
        if new_state == self._cache:
            # Steady state — nothing changed.
            return

        # Transition — emit audit + bus.
        self._audit_writer.write(
            "reconcile.cycle",
            {
                "any_fatal": any_fatal,
                "total_mismatches": total_mismatches,
                "pairs_reconciled": len(pairs),
            },
        )
        self._event_bus.publish(
            "reconcile.cycle",
            {
                "any_fatal": any_fatal,
                "total_mismatches": total_mismatches,
                "pairs_reconciled": len(pairs),
            },
        )
        self._cache = new_state

    def on_error(self, exc: Exception) -> None:
        """Isolated error policy for the reconcile cycle job.

        Writes ``reconcile.cycle_failed`` **once per failing episode**
        (anti-flood). Does **not** mutate ``session-scheduler`` status.
        Does **not** re-raise — APScheduler must not pause the job slot.
        """
        if not self._failing:
            self._audit_writer.write(
                "reconcile.cycle_failed",
                {"error": str(exc)},
            )
        self._failing = True
        logger.exception(
            "clay.scheduler: reconcile cycle failed; "
            "session-scheduler NOT marked ERROR (isolated policy)",
        )
