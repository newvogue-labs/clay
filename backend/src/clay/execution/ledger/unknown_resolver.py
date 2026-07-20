"""D-12d D3: Bounded-poll unknown-resolver (READ-ONLY).

Resolves UNKNOWN/SUBMITTING projections by polling venue truth with a
bounded budget. NEVER submits or resubmits — only transitions the ledger
to an observed state or leaves it as UNKNOWN (self-loop is legal).

Age-escalation: projections stuck in UNKNOWN beyond
``unknown_escalation_seconds`` are classified as FATAL (feeds D5 halt).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from clay.execution.ledger.controller import OrderLedgerController
from clay.execution.ledger.errors import IllegalTransitionError
from clay.execution.ledger.reconcile import ReconcileAdapter, map_venue_state
from clay.execution.ledger.repository import OrderLedgerRepository
from clay.execution.ledger.states import LedgerState

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UnknownResolverConfig:
    """Configuration for the unknown-resolver."""

    max_polls: int = 3
    backoff_seconds: float = 0.5
    escalation_seconds: int = 3600  # 1 hour → FATAL


@dataclass
class UnknownResolverReport:
    """Result of resolving unknowns for a single symbol."""

    resolved: list[str] = field(default_factory=list)
    still_unknown: list[str] = field(default_factory=list)
    escalated_to_fatal: list[str] = field(default_factory=list)


class UnknownResolver:
    """Bounded-poll resolver for UNKNOWN/SUBMITTING projections.

    READ-ONLY: polls venue truth to discover observed state.
    NEVER submits or resubmits orders.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker,  # type: ignore[type-arg]
        adapter: ReconcileAdapter,
        config: UnknownResolverConfig | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._adapter = adapter
        self._config = config or UnknownResolverConfig()
        self._now_fn = now_fn or (lambda: datetime.now(UTC))

    async def resolve_symbol(
        self,
        symbol: str,
        venue: str,
    ) -> UnknownResolverReport:
        """Resolve UNKNOWN/SUBMITTING projections for a single symbol.

        Algorithm:
        1. Load non-terminal projections for (venue, symbol)
        2. For each UNKNOWN/SUBMITTING projection:
           a. Bounded poll venue truth (up to max_polls)
           b. If venue match found → transition to observed state
           c. If no match after budget → leave as UNKNOWN
           d. If age > escalation_seconds → classify as FATAL
        """
        report = UnknownResolverReport()

        with self._session_factory() as s:
            repo = OrderLedgerRepository(s)
            active = repo.list_active_projections(venue=venue)

        # Filter to UNKNOWN/SUBMITTING for this symbol
        unknowns = [
            p
            for p in active
            if p.symbol == symbol
            and LedgerState(p.lifecycle_state)
            in {LedgerState.UNKNOWN, LedgerState.SUBMITTING}
        ]

        for proj in unknowns:
            cid = proj.client_order_id
            void = proj.venue_order_id

            # Age-escalation check
            age = (self._now_fn() - proj.updated_at).total_seconds()
            if age > self._config.escalation_seconds:
                report.escalated_to_fatal.append(cid)
                logger.info(
                    "unknown_resolver: escalation to FATAL for cid=%s (age=%.0fs)",
                    cid,
                    age,
                )
                continue

            # If no venue_order_id, can't poll — leave as UNKNOWN
            if void is None:
                report.still_unknown.append(cid)
                continue

            # Bounded poll venue truth
            resolved = await self._poll_venue_truth(
                symbol=symbol,
                venue_order_id=void,
                expected_cid=cid,
            )

            if resolved is not None:
                # Transition to observed state
                controller = OrderLedgerController(
                    self._session_factory, now_fn=self._now_fn
                )
                try:
                    with self._session_factory() as s:
                        repo = OrderLedgerRepository(s)
                        current = repo.get_projection(cid)
                        if current is None:
                            report.still_unknown.append(cid)
                            continue
                        current_version = current.version

                    controller.apply_transition(
                        client_order_id=cid,
                        expected_version=current_version,
                        to_state=resolved,
                        venue_order_id=void,
                        payload={
                            "reason_code": "UNKNOWN_RESOLVED",
                            "source": "unknown_resolver",
                        },
                    )
                    report.resolved.append(cid)
                except IllegalTransitionError:
                    # Can't transition — leave as UNKNOWN
                    report.still_unknown.append(cid)
            else:
                # No match after budget — leave as UNKNOWN
                report.still_unknown.append(cid)

        return report

    async def _poll_venue_truth(
        self,
        *,
        symbol: str,
        venue_order_id: str,
        expected_cid: str,
    ) -> LedgerState | None:
        """Poll venue truth with bounded budget.

        Returns the observed LedgerState if found, None if not found
        after exhausting the poll budget.
        """
        for _poll in range(self._config.max_polls):
            try:
                snapshots = await self._adapter.reconcile_orders(
                    symbol,
                    since=self._now_fn() - timedelta(seconds=300),
                )
                for snap in snapshots:
                    if (
                        snap.venue_order_id == venue_order_id
                        and snap.client_order_id == expected_cid
                    ):
                        return map_venue_state(snap.state)
            except Exception:
                logger.debug(
                    "unknown_resolver: poll failed for void=%s (attempt %d)",
                    venue_order_id,
                    _poll + 1,
                )

            # Short fixed backoff
            if _poll < self._config.max_polls - 1:
                await asyncio.sleep(self._config.backoff_seconds)

        return None
