"""D-12d D1: Write-around-place wiring for order ledger.

Wraps ``ExchangeAdapter.place_order`` with ledger lifecycle tracking:

1. ``record_intent`` before submit (creates projection in INTENT state)
2. ``apply_transition(SUBMITTING)`` before network call
3. ``apply_transition(ACKNOWLEDGED)`` on success (with venue_order_id)
4. ``apply_transition(UNKNOWN)`` on ambiguous failure

Crash between steps 2 and 3 leaves the projection in SUBMITTING/UNKNOWN —
the unknown-resolver (D3) picks it up on next reconcile tick.

Dormant by default (``CLAY_ORDER_LEDGER_ENABLED``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from clay.execution.adapter.domain import OrderAck, OrderRequest
from clay.execution.adapter.errors import (
    AmbiguousExecutionError,
    ConfigError,
    InsufficientFundsError,
    InvalidOrderError,
    OperationNotAllowedError,
    OrderRejectedError,
)
from clay.execution.ledger.controller import OrderLedgerController
from clay.execution.ledger.errors import (
    IllegalTransitionError,
)
from clay.execution.ledger.states import LedgerState

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker


logger = logging.getLogger(__name__)


class WriteAroundPlace:
    """Wrapper around ExchangeAdapter that adds ledger lifecycle tracking.

    Tracks order lifecycle through INTENT → SUBMITTING → ACKNOWLEDGED/UNKNOWN.
    Crash-safe: incomplete transitions leave projections in SUBMITTING/UNKNOWN
    for the unknown-resolver (D3) to pick up.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker,  # type: ignore[type-arg]
        venue: str,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._venue = venue
        self._now_fn = now_fn or (lambda: datetime.now(UTC))

    async def place_with_ledger(
        self,
        adapter,
        req: OrderRequest,
    ) -> OrderAck:
        """Place order with ledger lifecycle tracking.

        Steps:
        1. record_intent (creates INTENT projection)
        2. apply_transition(SUBMITTING) before network call
        3. adapter.place_order() — network call
        4. apply_transition(ACKNOWLEDGED) on success
        5. apply_transition(UNKNOWN) on ambiguous failure

        Raises DuplicateOrderIntentError on duplicate client_order_id.
        """
        controller = OrderLedgerController(self._session_factory, now_fn=self._now_fn)

        # Step 1: record_intent (creates INTENT projection)
        controller.record_intent(
            request=req,
            venue=self._venue,
        )
        client_order_id = req.client_order_id
        # Re-read version from DB (record_intent commits, detaching the object)
        with self._session_factory() as s:
            from clay.execution.ledger.repository import OrderLedgerRepository

            repo = OrderLedgerRepository(s)
            proj = repo.get_projection(client_order_id)
            current_version = proj.version if proj is not None else 0

        # Step 2: apply_transition(SUBMITTING) before network call
        try:
            proj = controller.apply_transition(
                client_order_id=client_order_id,
                expected_version=current_version,
                to_state=LedgerState.SUBMITTING,
                payload={
                    "reason_code": "SUBMITTING",
                    "source": "write_around_place",
                },
            )
            current_version = proj.version
        except IllegalTransitionError:
            # Already in SUBMITTING (idempotent) — re-read version
            with self._session_factory() as s:
                from clay.execution.ledger.repository import OrderLedgerRepository

                repo = OrderLedgerRepository(s)
                proj = repo.get_projection(client_order_id)
                if proj is not None:
                    current_version = proj.version
            logger.debug(
                "write_around_place: already in SUBMITTING for cid=%s",
                client_order_id,
            )

        # Step 3: network call
        try:
            ack = await adapter.place_order(req)
        except (
            OrderRejectedError,
            InsufficientFundsError,
            InvalidOrderError,
            ConfigError,
            OperationNotAllowedError,
        ) as exc:
            # Terminal errors — try to transition to REJECTED
            try:
                controller.apply_transition(
                    client_order_id=client_order_id,
                    expected_version=current_version,
                    to_state=LedgerState.REJECTED,
                    payload={
                        "reason_code": "PLACE_REJECTED",
                        "source": "write_around_place",
                        "error": str(exc),
                    },
                )
            except IllegalTransitionError:
                logger.debug(
                    "write_around_place: cannot transition to REJECTED for cid=%s",
                    client_order_id,
                )
            raise
        except AmbiguousExecutionError as exc:
            # Ambiguous — transition to UNKNOWN (unknown-resolver picks up)
            try:
                controller.apply_transition(
                    client_order_id=client_order_id,
                    expected_version=current_version,
                    to_state=LedgerState.UNKNOWN,
                    payload={
                        "reason_code": "PLACE_AMBIGUOUS",
                        "source": "write_around_place",
                        "error": str(exc),
                    },
                )
            except IllegalTransitionError:
                logger.debug(
                    "write_around_place: cannot transition to UNKNOWN for cid=%s",
                    client_order_id,
                )
            raise

        # Step 4: success — apply_transition(ACKNOWLEDGED) with venue_order_id
        try:
            controller.apply_transition(
                client_order_id=client_order_id,
                expected_version=current_version,
                to_state=LedgerState.ACKNOWLEDGED,
                venue_order_id=ack.venue_order_id,
                payload={
                    "reason_code": "PLACE_ACK",
                    "source": "write_around_place",
                    "venue_state": ack.state.value,
                },
            )
        except IllegalTransitionError:
            logger.debug(
                "write_around_place: cannot transition to ACKNOWLEDGED for cid=%s",
                client_order_id,
            )

        return ack
