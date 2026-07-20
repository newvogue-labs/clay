"""D-12d D2: Startup-reconciliation before execution-gate opens.

Hook on startup: iterate list_active_projections() (non-terminal) and
reconcile with venue BEFORE the gate starts admitting place_order calls.

Fail-closed when venue is unavailable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from clay.execution.ledger.reconcile import OrderReconcileService
from clay.execution.ledger.repository import OrderLedgerRepository
from clay.execution.ledger.unknown_resolver import UnknownResolver

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from clay.execution.ledger.fatal_halt import FatalHaltWiring


logger = logging.getLogger(__name__)


class StartupReconciliation:
    """Startup hook that reconciles all non-terminal projections before gate opens.

    Fail-closed: if venue is unavailable, the gate does NOT open.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker,  # type: ignore[type-arg]
        reconcile_service: OrderReconcileService,
        unknown_resolver: UnknownResolver | None = None,
        now_fn: Callable[[], datetime] | None = None,
        fatal_halt_wiring: FatalHaltWiring | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._reconcile_service = reconcile_service
        self._unknown_resolver = unknown_resolver
        self._now_fn = now_fn or (lambda: datetime.now(UTC))
        self._fatal_halt_wiring = fatal_halt_wiring

    async def run_startup_reconciliation(self) -> bool:
        """Run startup reconciliation before gate opens.

        Returns True if all projections are resolved (gate can open).
        Returns False if any UNKNOWN projections remain (gate stays closed).

        Algorithm:
        1. Load non-terminal projections
        2. For each (venue, symbol) pair: reconcile with venue
        3. Run unknown-resolver on remaining UNKNOWNs
        4. Return True only if no UNKNOWN/SUBMITTING projections remain
        """
        with self._session_factory() as s:
            repo = OrderLedgerRepository(s)
            active = repo.list_active_projections()

        if not active:
            logger.info("startup_reconciliation: no active projections")
            return True

        # Deduplicate to distinct (venue, symbol) pairs
        pairs: set[tuple[str, str]] = set()
        for p in active:
            if p.venue and p.symbol:
                pairs.add((p.venue, p.symbol))

        logger.info(
            "startup_reconciliation: %d active projections, %d (venue, symbol) pairs",
            len(active),
            len(pairs),
        )

        # Reconcile each pair
        any_fatal = False
        for venue, symbol in sorted(pairs):
            try:
                since = self._now_fn()
                report = await self._reconcile_service.reconcile_symbol(
                    symbol, since, venue=venue
                )
                if report.has_fatal:
                    any_fatal = True
                    # D-15: engage halt-latch when wiring is bound
                    if self._fatal_halt_wiring is not None:
                        self._fatal_halt_wiring.on_fatal_report(
                            report, venue=venue, symbol=symbol
                        )
                    logger.warning(
                        "startup_reconciliation: fatal mismatch for %s/%s",
                        venue,
                        symbol,
                    )
            except Exception:
                logger.exception(
                    "startup_reconciliation: reconcile failed for %s/%s",
                    venue,
                    symbol,
                )
                # Fail-closed: return False on any error
                return False

        # Run unknown-resolver if available
        if self._unknown_resolver is not None:
            for venue, symbol in sorted(pairs):
                try:
                    report = await self._unknown_resolver.resolve_symbol(symbol, venue)
                    if report.escalated_to_fatal:
                        any_fatal = True
                        # D-15: engage halt-latch on age-escalation when wiring is bound
                        if self._fatal_halt_wiring is not None:
                            self._fatal_halt_wiring.on_escalated_fatal(
                                venue=venue,
                                symbol=symbol,
                                escalated_cids=report.escalated_to_fatal,
                            )
                except Exception:
                    logger.exception(
                        "startup_reconciliation: unknown-resolver failed for %s/%s",
                        venue,
                        symbol,
                    )
                    return False

        # Check if any UNKNOWN/SUBMITTING projections remain
        with self._session_factory() as s:
            repo = OrderLedgerRepository(s)
            remaining = repo.list_active_projections()

        from clay.execution.ledger.states import LedgerState

        unresolved = [
            p
            for p in remaining
            if LedgerState(p.lifecycle_state)
            in {LedgerState.UNKNOWN, LedgerState.SUBMITTING}
        ]

        if unresolved or any_fatal:
            logger.warning(
                "startup_reconciliation: %d unresolved projections remain, "
                "gate stays closed",
                len(unresolved),
            )
            return False

        logger.info("startup_reconciliation: all projections resolved")
        return True
