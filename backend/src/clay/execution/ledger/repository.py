"""Order Ledger repository — CRUD + optimistic-CAS for projections."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from clay.db.models_orders import OrderCurrentState, OrderEvent, OrderFillRecord


class OrderLedgerRepository:
    """Data-access layer for order ledger tables.

    Follows the pattern of :class:`clay.db.repositories_ops.OpsRepository`:
    takes ``Session`` in the constructor, uses ``add()`` + ``flush()``,
    commits on the caller side.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def append_event(self, event: OrderEvent) -> None:
        """Append a lifecycle event (INSERT-only, no UPDATE/DELETE)."""
        self.session.add(event)
        self.session.flush()

    def get_projection(self, client_order_id: str) -> OrderCurrentState | None:
        """Retrieve the current-state projection for an order."""
        return self.session.get(OrderCurrentState, client_order_id)

    def insert_projection(self, row: OrderCurrentState) -> None:
        """Insert a new current-state projection."""
        self.session.add(row)
        self.session.flush()

    def cas_update_projection(
        self,
        *,
        client_order_id: str,
        expected_version: int,
        lifecycle_state: str,
        last_event_id: str,
        updated_at: datetime,
        venue_order_id: str | None = None,
        filled_qty: str | None = None,
    ) -> int:
        """Optimistic-CAS update on the projection row.

        Updates only when ``version == expected_version``.
        Increments ``version`` by 1 on success.

        Returns the number of rows affected (0 or 1).
        """
        values: dict[str, object] = {
            "lifecycle_state": lifecycle_state,
            "last_event_id": last_event_id,
            "updated_at": updated_at,
        }
        if venue_order_id is not None:
            values["venue_order_id"] = venue_order_id
        if filled_qty is not None:
            values["filled_qty"] = filled_qty

        stmt = (
            update(OrderCurrentState)
            .where(
                OrderCurrentState.client_order_id == client_order_id,
                OrderCurrentState.version == expected_version,
            )
            .values(
                version=OrderCurrentState.version + 1,
                **values,
            )
        )
        result = self.session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # D-12a-3: fill-record methods
    # ------------------------------------------------------------------

    def existing_trade_ids(self, venue: str, trade_ids: list[str]) -> set[str]:
        """Вернуть подмножество ``trade_id``, уже присутствующих в ``fills``.

        На вход — список trade_id для проверки. На выход — те, что уже
        есть в таблице ``OrderFillRecord`` для данного ``venue``.
        """
        if not trade_ids:
            return set()
        stmt = select(OrderFillRecord.trade_id).where(
            OrderFillRecord.venue == venue,
            OrderFillRecord.trade_id.in_(trade_ids),
        )
        return set(self.session.execute(stmt).scalars())

    def insert_fills(self, records: list[OrderFillRecord]) -> None:
        """Батч-вставка ``OrderFillRecord``.

         Все записи должны быть уникальны по ``(venue, trade_id)`` —
        caller обязан отфильтровать дубли через :meth:`existing_trade_ids`.
        """
        self.session.add_all(records)
        self.session.flush()

    def get_fill_quantities(self, client_order_id: str) -> list[str]:
        """Вернуть все ``quantity`` (Text) для данного ордера.

        Суммирование происходит в приложении (Decimal), а не через
        серверный ``SUM`` по Text-колонке.
        """
        stmt = select(OrderFillRecord.quantity).where(
            OrderFillRecord.client_order_id == client_order_id
        )
        return list(self.session.execute(stmt).scalars())
