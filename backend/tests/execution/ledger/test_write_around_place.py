"""Tests for D-12d D1: write-around-place wiring."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from clay.db import models_orders  # noqa: F401 — register tables
from clay.db.base import Base
from clay.db.session import SQLITE_SCHEMA_TRANSLATE_MAP
from clay.execution.adapter.domain import OrderAck, OrderRequest
from clay.execution.adapter.enums import (
    OrderSide,
    OrderState,
    OrderType,
    TimeInForce,
)
from clay.execution.adapter.errors import (
    AmbiguousExecutionError,
    OrderRejectedError,
)
from clay.execution.ledger.errors import DuplicateOrderIntentError
from clay.execution.ledger.states import LedgerState
from clay.execution.ledger.write_around_place import WriteAroundPlace


def _make_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": SQLITE_SCHEMA_TRANSLATE_MAP},
    )


def _make_request(
    *,
    symbol: str = "BTCUSDT",
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.LIMIT,
    quantity: Decimal = Decimal("0.001"),
    price: Decimal = Decimal("50000"),
    client_order_id: str = "test-cid-001",
) -> OrderRequest:
    return OrderRequest(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        time_in_force=TimeInForce.GTC,
        client_order_id=client_order_id,
        price=price,
    )


def _make_ack(
    *,
    client_order_id: str = "test-cid-001",
    venue_order_id: str = "venue-001",
    state: OrderState = OrderState.NEW,
) -> OrderAck:
    return OrderAck(
        client_order_id=client_order_id,
        venue_order_id=venue_order_id,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        state=state,
        quantity=Decimal("0.001"),
        price=Decimal("50000"),
        transact_time=int(datetime.now(UTC).timestamp() * 1000),
        fills=(),
    )


@pytest.fixture()
def session_factory():
    """In-memory SQLite session factory."""
    engine = _make_engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture()
def write_around(session_factory):
    """WriteAroundPlace with a fresh session."""
    return WriteAroundPlace(session_factory=session_factory, venue="bybit")


class TestWriteAroundPlace:
    @pytest.mark.asyncio
    async def test_success_path(
        self, session_factory, write_around: WriteAroundPlace
    ) -> None:
        """Successful place: INTENT → SUBMITTING → ACKNOWLEDGED."""
        mock_adapter = AsyncMock()
        mock_adapter.place_order.return_value = _make_ack()

        req = _make_request()
        ack = await write_around.place_with_ledger(mock_adapter, req)

        assert ack.venue_order_id == "venue-001"

        # Verify projection is in ACKNOWLEDGED state
        with session_factory() as s:
            from sqlalchemy import select
            from clay.db.models_orders import OrderCurrentState

            proj = (
                s.execute(
                    select(OrderCurrentState).where(
                        OrderCurrentState.client_order_id == "test-cid-001"
                    )
                )
                .scalars()
                .one()
            )
            assert proj.lifecycle_state == LedgerState.ACKNOWLEDGED.value
            assert proj.venue_order_id == "venue-001"

    @pytest.mark.asyncio
    async def test_ambiguous_failure_transitions_to_unknown(
        self, session_factory, write_around: WriteAroundPlace
    ) -> None:
        """AmbiguousExecutionError → UNKNOWN state."""
        mock_adapter = AsyncMock()
        mock_adapter.place_order.side_effect = AmbiguousExecutionError("timeout")

        req = _make_request()
        with pytest.raises(AmbiguousExecutionError):
            await write_around.place_with_ledger(mock_adapter, req)

        # Verify projection is in UNKNOWN state
        with session_factory() as s:
            from sqlalchemy import select
            from clay.db.models_orders import OrderCurrentState

            proj = (
                s.execute(
                    select(OrderCurrentState).where(
                        OrderCurrentState.client_order_id == "test-cid-001"
                    )
                )
                .scalars()
                .one()
            )
            assert proj.lifecycle_state == LedgerState.UNKNOWN.value

    @pytest.mark.asyncio
    async def test_rejected_failure_transitions_to_rejected(
        self, session_factory, write_around: WriteAroundPlace
    ) -> None:
        """OrderRejectedError → REJECTED state."""
        mock_adapter = AsyncMock()
        mock_adapter.place_order.side_effect = OrderRejectedError("rejected")

        req = _make_request()
        with pytest.raises(OrderRejectedError):
            await write_around.place_with_ledger(mock_adapter, req)

        # Verify projection is in REJECTED state
        with session_factory() as s:
            from sqlalchemy import select
            from clay.db.models_orders import OrderCurrentState

            proj = (
                s.execute(
                    select(OrderCurrentState).where(
                        OrderCurrentState.client_order_id == "test-cid-001"
                    )
                )
                .scalars()
                .one()
            )
            assert proj.lifecycle_state == LedgerState.REJECTED.value

    @pytest.mark.asyncio
    async def test_duplicate_intent_raises(
        self, session_factory, write_around: WriteAroundPlace
    ) -> None:
        """Duplicate client_order_id → DuplicateOrderIntentError."""
        mock_adapter = AsyncMock()
        mock_adapter.place_order.return_value = _make_ack()

        req = _make_request()
        await write_around.place_with_ledger(mock_adapter, req)

        # Second call with same cid should raise
        with pytest.raises(DuplicateOrderIntentError):
            await write_around.place_with_ledger(mock_adapter, req)

    @pytest.mark.asyncio
    async def test_crash_between_create_and_ack_leaves_submitted(
        self, session_factory, write_around: WriteAroundPlace
    ) -> None:
        """Crash after SUBMITTING but before ACK leaves projection in SUBMITTING."""
        mock_adapter = AsyncMock()
        # Simulate crash during place_order
        mock_adapter.place_order.side_effect = Exception("crash")

        req = _make_request()
        with pytest.raises(Exception, match="crash"):
            await write_around.place_with_ledger(mock_adapter, req)

        # Verify projection is in SUBMITTING state
        with session_factory() as s:
            from sqlalchemy import select
            from clay.db.models_orders import OrderCurrentState

            proj = (
                s.execute(
                    select(OrderCurrentState).where(
                        OrderCurrentState.client_order_id == "test-cid-001"
                    )
                )
                .scalars()
                .one()
            )
            assert proj.lifecycle_state == LedgerState.SUBMITTING.value
