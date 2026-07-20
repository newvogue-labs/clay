"""Tests for D-12d D3: bounded-poll unknown-resolver."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from clay.db import models_orders  # noqa: F401 — register tables
from clay.db.base import Base
from clay.db.session import SQLITE_SCHEMA_TRANSLATE_MAP
from clay.execution.adapter.domain import OrderSnapshot
from clay.execution.adapter.enums import (
    OrderSide,
    OrderState,
    OrderType,
)
from clay.execution.ledger.states import LedgerState
from clay.execution.ledger.unknown_resolver import (
    UnknownResolver,
    UnknownResolverConfig,
)


def _make_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": SQLITE_SCHEMA_TRANSLATE_MAP},
    )


def _make_snapshot(
    *,
    client_order_id: str = "test-cid-001",
    venue_order_id: str = "venue-001",
    state: OrderState = OrderState.NEW,
) -> OrderSnapshot:
    return OrderSnapshot(
        client_order_id=client_order_id,
        venue_order_id=venue_order_id,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        state=state,
        quantity=Decimal("0.001"),
        executed_qty=Decimal("0"),
        price=Decimal("50000"),
        transact_time=int(datetime.now(UTC).timestamp() * 1000),
        fills=(),
    )


class FakeReconcileAdapter:
    """Fake adapter for testing unknown-resolver."""

    def __init__(self) -> None:
        self.reconcile_result: list[OrderSnapshot] = []
        self.call_count = 0

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]:
        self.call_count += 1
        return self.reconcile_result

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderSnapshot]:
        return []

    async def get_my_trades(
        self, symbol: str, *, since: datetime | None = None, from_id: str | None = None
    ):
        return []


@pytest.fixture()
def session_factory():
    """In-memory SQLite session factory."""
    engine = _make_engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def _create_unknown_projection(session_factory, *, cid: str = "test-cid-001") -> None:
    """Helper: create a projection in UNKNOWN state."""
    from clay.db.models_orders import OrderCurrentState
    from datetime import UTC, datetime

    with session_factory() as s:
        proj = OrderCurrentState(
            client_order_id=cid,
            venue="bybit",
            symbol="BTCUSDT",
            venue_order_id="venue-001",
            lifecycle_state=LedgerState.UNKNOWN,
            filled_qty="0",
            last_event_id="evt-001",
            semantic_hash=None,
            version=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(proj)
        s.commit()


class TestUnknownResolver:
    @pytest.mark.asyncio
    async def test_resolve_unknown_to_filled(
        self, session_factory
    ) -> None:
        """UNKNOWN projection with venue match → FILLED."""
        _create_unknown_projection(session_factory)

        adapter = FakeReconcileAdapter()
        adapter.reconcile_result = [
            _make_snapshot(state=OrderState.FILLED)
        ]

        resolver = UnknownResolver(
            session_factory=session_factory,
            adapter=adapter,
            config=UnknownResolverConfig(max_polls=1),
        )

        report = await resolver.resolve_symbol("BTCUSDT", "bybit")

        assert "test-cid-001" in report.resolved
        assert "test-cid-001" not in report.still_unknown

        # Verify projection is now FILLED
        with session_factory() as s:
            from sqlalchemy import select
            from clay.db.models_orders import OrderCurrentState

            proj = s.execute(
                select(OrderCurrentState).where(
                    OrderCurrentState.client_order_id == "test-cid-001"
                )
            ).scalars().one()
            assert proj.lifecycle_state == LedgerState.FILLED.value

    @pytest.mark.asyncio
    async def test_poll_budget_exhausted_stays_unknown(
        self, session_factory
    ) -> None:
        """No venue match after budget → still UNKNOWN."""
        _create_unknown_projection(session_factory)

        adapter = FakeReconcileAdapter()
        adapter.reconcile_result = []  # no matches

        resolver = UnknownResolver(
            session_factory=session_factory,
            adapter=adapter,
            config=UnknownResolverConfig(max_polls=2, backoff_seconds=0.01),
        )

        report = await resolver.resolve_symbol("BTCUSDT", "bybit")

        assert "test-cid-001" in report.still_unknown
        assert "test-cid-001" not in report.resolved
        assert adapter.call_count == 2

    @pytest.mark.asyncio
    async def test_escalation_to_fatal(
        self, session_factory
    ) -> None:
        """UNKNOWN age > escalation_seconds → FATAL."""
        # Create projection with old updated_at
        from clay.db.models_orders import OrderCurrentState

        with session_factory() as s:
            proj = OrderCurrentState(
                client_order_id="old-cid",
                venue="bybit",
                symbol="BTCUSDT",
                venue_order_id="venue-001",
                lifecycle_state=LedgerState.UNKNOWN,
                filled_qty="0",
                last_event_id="evt-001",
                semantic_hash=None,
                version=0,
                created_at=datetime.now(UTC) - timedelta(hours=2),
                updated_at=datetime.now(UTC) - timedelta(hours=2),
            )
            s.add(proj)
            s.commit()

        adapter = FakeReconcileAdapter()
        resolver = UnknownResolver(
            session_factory=session_factory,
            adapter=adapter,
            config=UnknownResolverConfig(escalation_seconds=3600),
        )

        report = await resolver.resolve_symbol("BTCUSDT", "bybit")

        assert "old-cid" in report.escalated_to_fatal
        assert adapter.call_count == 0  # no poll needed

    @pytest.mark.asyncio
    async def test_no_venue_order_id_stays_unknown(
        self, session_factory
    ) -> None:
        """Projection without venue_order_id → can't poll, stays UNKNOWN."""
        from clay.db.models_orders import OrderCurrentState

        with session_factory() as s:
            proj = OrderCurrentState(
                client_order_id="no-void-cid",
                venue="bybit",
                symbol="BTCUSDT",
                venue_order_id=None,  # no venue_order_id
                lifecycle_state=LedgerState.UNKNOWN,
                filled_qty="0",
                last_event_id="evt-001",
                semantic_hash=None,
                version=0,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(proj)
            s.commit()

        adapter = FakeReconcileAdapter()
        resolver = UnknownResolver(
            session_factory=session_factory,
            adapter=adapter,
        )

        report = await resolver.resolve_symbol("BTCUSDT", "bybit")

        assert "no-void-cid" in report.still_unknown
        assert adapter.call_count == 0

    @pytest.mark.asyncio
    async def test_zero_place_order_calls(
        self, session_factory
    ) -> None:
        """Resolver NEVER calls place_order — only polls."""
        _create_unknown_projection(session_factory)

        adapter = FakeReconcileAdapter()
        adapter.reconcile_result = [
            _make_snapshot(state=OrderState.NEW)
        ]

        resolver = UnknownResolver(
            session_factory=session_factory,
            adapter=adapter,
            config=UnknownResolverConfig(max_polls=1),
        )

        await resolver.resolve_symbol("BTCUSDT", "bybit")

        # Verify resolver never called place_order
        assert not hasattr(adapter, 'place_order') or not callable(getattr(adapter, 'place_order', None))
