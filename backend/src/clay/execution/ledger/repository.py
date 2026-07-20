"""Order Ledger repository — CRUD + optimistic-CAS for projections."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from clay.db.models_orders import (
    OrderCurrentState,
    OrderEvent,
    OrderFillRecord,
    ReconcileBookmark,
)
from clay.execution.ledger.states import TERMINAL_STATES


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

    # ------------------------------------------------------------------
    # D-12b-1: reconcile read-side
    # ------------------------------------------------------------------

    def list_active_projections(
        self, venue: str | None = None
    ) -> list[OrderCurrentState]:
        """Вернуть проекции, чей lifecycle_state НЕ терминален.

        При ``venue`` — фильтр по venue.
        """
        stmt = select(OrderCurrentState).where(
            ~OrderCurrentState.lifecycle_state.in_([s.value for s in TERMINAL_STATES])
        )
        if venue is not None:
            stmt = stmt.where(OrderCurrentState.venue == venue)
        return list(self.session.execute(stmt).scalars())

    def get_projection_by_venue_order_id(
        self, venue: str, venue_order_id: str
    ) -> OrderCurrentState | None:
        """Найти проекцию по ``(venue, venue_order_id)``.

        Использует существующий индекс ``ix_order_current_state_venue_venue_order_id``.
        """
        stmt = select(OrderCurrentState).where(
            OrderCurrentState.venue == venue,
            OrderCurrentState.venue_order_id == venue_order_id,
        )
        return self.session.execute(stmt).scalars().one_or_none()

    # ------------------------------------------------------------------
    # D-12b-2: reconcile bookmark
    # ------------------------------------------------------------------

    def get_reconcile_bookmark(
        self, *, venue: str, entity_type: str, symbol: str
    ) -> ReconcileBookmark | None:
        """Получить bookmark ``(venue, entity_type, symbol)``."""
        stmt = select(ReconcileBookmark).where(
            ReconcileBookmark.venue == venue,
            ReconcileBookmark.entity_type == entity_type,
            ReconcileBookmark.symbol == symbol,
        )
        return self.session.execute(stmt).scalars().one_or_none()

    def upsert_reconcile_bookmark(
        self,
        *,
        venue: str,
        entity_type: str,
        symbol: str,
        last_trade_id: str,
        last_timestamp: int,
        now: datetime,
    ) -> None:
        """Insert или update bookmark для ``(venue, entity_type, symbol)``.

        SQLite-portable: select-then-update-or-insert, commit на вызывающем.
        """
        existing = self.get_reconcile_bookmark(
            venue=venue, entity_type=entity_type, symbol=symbol
        )
        if existing is not None:
            existing.last_trade_id = last_trade_id
            existing.last_timestamp = last_timestamp
            existing.updated_at = now
        else:
            self.session.add(
                ReconcileBookmark(
                    venue=venue,
                    entity_type=entity_type,
                    symbol=symbol,
                    last_trade_id=last_trade_id,
                    last_timestamp=last_timestamp,
                    updated_at=now,
                )
            )
        self.session.flush()
