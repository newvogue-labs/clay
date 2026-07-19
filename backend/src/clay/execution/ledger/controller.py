"""Order Ledger controller — atomic write-path for intent + transitions.

Dormant by default (``CLAY_ORDER_LEDGER_ENABLED``).
Not yet wired to any production code path.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from clay.db.models_orders import OrderCurrentState, OrderEvent, OrderFillRecord
from clay.execution.adapter.domain import Fill, OrderRequest
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

    def record_fills(
        self,
        *,
        client_order_id: str,
        fills: list[Fill],
        to_state: LedgerState,
        expected_version: int,
    ) -> OrderCurrentState:
        """Записать trade-fills с дедупом и пересчётом ``filled``.

        Атомарная транзакция (7 шагов):

        1. Загрузить проекцию по ``client_order_id`` → ``OrderNotInLedgerError``.
        2. ``venue`` из проекции.
        3. Дедуп: оставить только недостающие ``(venue, trade_id)``.
        4. Батч-вставка ``OrderFillRecord`` для недостающих.
        5. Пересчёт ``filled`` = сумма ``Decimal`` по всем ``quantity`` ордера.
        6. Append lifecycle-события ``order_events``.
        7. CAS-переход в ``to_state`` с FSM + ``expected_version``.

        D5 — идемпотентность:
        - Если после дедупа новых fills ``нет`` И ``to_state`` == текущее
          состояние → no-op (без вставок, события, роста ``version``).
        - Если новые fills есть → событие пишем всегда, включая
          ``PARTIALLY_FILLED → PARTIALLY_FILLED``.

        D6 — контроллер НЕ выводит терминальный ``FILLED``:
        ``to_state`` всегда приходит параметром, контроллер только
        энфорсит FSM-легальность.
        """
        now = self._now_fn()

        with self._session_factory() as s:
            repo = OrderLedgerRepository(s)

            # --- Шаг 1: загрузка проекции ---
            proj = repo.get_projection(client_order_id)
            if proj is None:
                raise OrderNotInLedgerError(
                    f"No projection for client_order_id={client_order_id!r}"
                )

            # --- Шаг 2: venue из проекции ---
            venue = proj.venue

            # --- Шаг 3: дедуп ---
            incoming_ids = [f.trade_id for f in fills]
            existing = repo.existing_trade_ids(venue, incoming_ids)
            missing_fills = [f for f in fills if f.trade_id not in existing]

            from_state = LedgerState(proj.lifecycle_state)

            # --- FSM-проверка (до любых мутаций) ---
            if not is_legal_transition(from_state, to_state):
                raise IllegalTransitionError(from_state, to_state)

            # --- D5: идемпотентность ---
            if not missing_fills and to_state == from_state:
                # No-op: ничего не меняем
                return proj  # type: ignore[return-value]

            # --- Шаг 4: батч-вставка ---
            now_utc = now
            if missing_fills:
                records = [
                    OrderFillRecord(
                        venue=venue,
                        trade_id=f.trade_id,
                        venue_order_id=f.venue_order_id,
                        client_order_id=client_order_id,
                        symbol=f.symbol,
                        side=str(f.side),
                        quantity=str(f.quantity),
                        price=str(f.price),
                        commission=str(f.commission),
                        commission_asset=f.commission_asset,
                        transact_time=f.transact_time,
                        created_at=now_utc,
                    )
                    for f in missing_fills
                ]
                repo.insert_fills(records)

            # --- Шаг 5: пересчёт filled ---
            all_quantities = repo.get_fill_quantities(client_order_id)
            filled = sum((Decimal(q) for q in all_quantities), Decimal("0"))
            filled_str = str(filled)

            # --- Шаг 6: lifecycle-событие ---
            event_id = str(uuid4())
            event = OrderEvent(
                event_id=event_id,
                client_order_id=client_order_id,
                venue_order_id=missing_fills[0].venue_order_id
                if missing_fills
                else None,
                venue=venue,
                symbol=proj.symbol,
                event_type=to_state,
                semantic_hash=proj.semantic_hash,
                payload=json.dumps(
                    {
                        "fills_count": len(missing_fills),
                        "filled_qty": filled_str,
                        "idempotent": len(missing_fills) == 0,
                    },
                    sort_keys=True,
                ),
                created_at=now_utc,
            )
            repo.append_event(event)

            # --- Шаг 7: CAS-переход ---
            rc = repo.cas_update_projection(
                client_order_id=client_order_id,
                expected_version=expected_version,
                lifecycle_state=to_state,
                last_event_id=event_id,
                updated_at=now_utc,
                filled_qty=filled_str,
            )
            if rc != 1:
                s.rollback()
                raise ConcurrencyConflictError(
                    f"CAS failed for client_order_id={client_order_id!r}, "
                    f"expected_version={expected_version}"
                )
            s.commit()

        return repo.get_projection(client_order_id)  # type: ignore[return-value]
