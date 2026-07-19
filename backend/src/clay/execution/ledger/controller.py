"""Order Ledger controller — atomic write-path for intent + transitions.

Dormant by default (``CLAY_ORDER_LEDGER_ENABLED``).
Not yet wired to any production code path.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from clay.db.models_orders import OrderCurrentState, OrderEvent
from clay.execution.adapter.domain import OrderRequest
from clay.execution.ledger.errors import (
    ConcurrencyConflictError,
    DuplicateOrderIntentError,
    IllegalTransitionError,
    OrderNotInLedgerError,
)
from clay.execution.ledger.fsm import is_legal_transition
from clay.execution.ledger.repository import OrderLedgerRepository
from clay.execution.ledger.states import LedgerState
from clay.execution.proof.checker import semantic_intent_hash


class OrderLedgerController:
    """Atomic write-path for order lifecycle events and projections.

    Two operations:

    - ``record_intent``: inserts INTENT event + projection (idempotent on CID).
    - ``apply_transition``: validates FSM, appends event, CAS-updates projection.

    Neither operation has callers in the production code path yet — this
    controller is the write-side foundation, wired in a later slice.
    """

    def __init__(
        self,
        session_factory: sessionmaker,  # type: ignore[type-arg]
        *,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now_fn = now_fn or (lambda: datetime.now(UTC))

    def record_intent(
        self,
        *,
        request: OrderRequest,
        venue: str,
    ) -> OrderCurrentState:
        """Record the first lifecycle event (INTENT) and create the projection.

        Atomically:
        - INSERT into ``order_events``
        - INSERT into ``order_current_state``

        Raises :class:`DuplicateOrderIntentError` on UNIQUE violation
        (client_order_id already exists). The database is left clean:
        no orphan events, no duplicate projection.
        """
        now = self._now_fn()
        event_id = str(uuid4())
        sem = semantic_intent_hash(request)
        payload = json.dumps(
            {
                "symbol": request.symbol,
                "side": str(request.side),
                "order_type": str(request.order_type),
                "quantity": str(request.quantity),
                "time_in_force": str(request.time_in_force),
                "client_order_id": request.client_order_id,
                "price": str(request.price) if request.price is not None else None,
                "stop_price": (
                    str(request.stop_price) if request.stop_price is not None else None
                ),
            },
            sort_keys=True,
        )

        with self._session_factory() as s:
            repo = OrderLedgerRepository(s)

            event = OrderEvent(
                event_id=event_id,
                client_order_id=request.client_order_id,
                venue_order_id=None,
                venue=venue,
                symbol=request.symbol,
                event_type=LedgerState.INTENT,
                semantic_hash=sem,
                payload=payload,
                created_at=now,
            )
            repo.append_event(event)

            projection = OrderCurrentState(
                client_order_id=request.client_order_id,
                venue=venue,
                symbol=request.symbol,
                venue_order_id=None,
                lifecycle_state=LedgerState.INTENT,
                filled_qty="0",
                last_event_id=event_id,
                semantic_hash=sem,
                version=0,
                created_at=now,
                updated_at=now,
            )
            try:
                repo.insert_projection(projection)
            except IntegrityError:
                s.rollback()
                raise DuplicateOrderIntentError(
                    f"Intent already recorded for client_order_id="
                    f"{request.client_order_id!r}"
                )
            s.commit()

        return projection

    def apply_transition(
        self,
        *,
        client_order_id: str,
        expected_version: int,
        to_state: LedgerState,
        event_type: str | None = None,
        venue_order_id: str | None = None,
        filled_qty: str | None = None,
        payload: dict | None = None,
    ) -> OrderCurrentState:
        """Atomically validate FSM, append event, and CAS-update projection.

        Steps:
        1. Load projection (or raise ``OrderNotInLedgerError``).
        2. Check FSM transition (or raise ``IllegalTransitionError``).
        3. Append event to ``order_events``.
        4. CAS-update projection with version check.

        On CAS failure (``rc != 1``), the entire transaction is rolled back:
        no orphan events remain.
        """
        now = self._now_fn()

        with self._session_factory() as s:
            repo = OrderLedgerRepository(s)

            proj = repo.get_projection(client_order_id)
            if proj is None:
                raise OrderNotInLedgerError(
                    f"No projection for client_order_id={client_order_id!r}"
                )

            from_state = LedgerState(proj.lifecycle_state)
            if not is_legal_transition(from_state, to_state):
                raise IllegalTransitionError(from_state, to_state)

            event_id = str(uuid4())
            event = OrderEvent(
                event_id=event_id,
                client_order_id=client_order_id,
                venue_order_id=venue_order_id,
                venue=proj.venue,
                symbol=proj.symbol,
                event_type=event_type or to_state,
                semantic_hash=proj.semantic_hash,
                payload=json.dumps(payload or {}, sort_keys=True),
                created_at=now,
            )
            repo.append_event(event)

            rc = repo.cas_update_projection(
                client_order_id=client_order_id,
                expected_version=expected_version,
                lifecycle_state=to_state,
                last_event_id=event_id,
                updated_at=now,
                venue_order_id=venue_order_id,
                filled_qty=filled_qty,
            )
            if rc != 1:
                s.rollback()
                raise ConcurrencyConflictError(
                    f"CAS failed for client_order_id={client_order_id!r}, "
                    f"expected_version={expected_version}"
                )
            s.commit()

        return repo.get_projection(client_order_id)  # type: ignore[return-value]
