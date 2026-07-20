"""Tests for D-12d D2: startup-reconciliation before execution-gate."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from clay.db import models_orders  # noqa: F401 — register tables
from clay.db.base import Base
from clay.db.session import SQLITE_SCHEMA_TRANSLATE_MAP
from clay.execution.adapter.domain import OrderSnapshot
from clay.execution.ledger.reconcile import OrderReconcileService
from clay.execution.ledger.states import LedgerState
from clay.execution.ledger.startup_reconciliation import StartupReconciliation


def _make_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": SQLITE_SCHEMA_TRANSLATE_MAP},
    )


class FakeReconcileAdapter:
    """Fake adapter for testing startup reconciliation."""

    def __init__(self) -> None:
        self.reconcile_result: list[OrderSnapshot] = []
        self.open_orders_result: list[OrderSnapshot] = []
        self.trades_result = []

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]:
        return self.reconcile_result

    async def get_open_orders(self, symbol=None) -> list[OrderSnapshot]:
        return self.open_orders_result

    async def get_my_trades(self, symbol, *, since=None, from_id=None):
        return self.trades_result


def _create_projection(session_factory, *, cid: str, state: LedgerState) -> None:
    """Helper: create a projection in the given state."""
    from clay.db.models_orders import OrderCurrentState

    with session_factory() as s:
        proj = OrderCurrentState(
            client_order_id=cid,
            venue="bybit",
            symbol="BTCUSDT",
            venue_order_id="venue-001" if state != LedgerState.INTENT else None,
            lifecycle_state=state,
            filled_qty="0",
            last_event_id="evt-001",
            semantic_hash=None,
            version=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(proj)
        s.commit()


@pytest.fixture()
def session_factory():
    """In-memory SQLite session factory."""
    engine = _make_engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


class TestStartupReconciliation:
    @pytest.mark.asyncio
    async def test_no_projections_returns_true(self, session_factory) -> None:
        """No active projections → return True (gate can open)."""
        adapter = FakeReconcileAdapter()
        reconcile_service = OrderReconcileService(
            session_factory=session_factory,
            adapter=adapter,
        )

        startup = StartupReconciliation(
            session_factory=session_factory,
            reconcile_service=reconcile_service,
        )

        result = await startup.run_startup_reconciliation()

        assert result is True

    @pytest.mark.asyncio
    async def test_resolved_projections_returns_true(self, session_factory) -> None:
        """All projections resolved → return True."""
        _create_projection(session_factory, cid="cid-001", state=LedgerState.FILLED)

        adapter = FakeReconcileAdapter()
        reconcile_service = OrderReconcileService(
            session_factory=session_factory,
            adapter=adapter,
        )

        startup = StartupReconciliation(
            session_factory=session_factory,
            reconcile_service=reconcile_service,
        )

        result = await startup.run_startup_reconciliation()

        assert result is True

    @pytest.mark.asyncio
    async def test_unknown_projection_returns_false(self, session_factory) -> None:
        """UNKNOWN projection remains → return False (gate stays closed)."""
        _create_projection(session_factory, cid="cid-001", state=LedgerState.UNKNOWN)

        adapter = FakeReconcileAdapter()
        reconcile_service = OrderReconcileService(
            session_factory=session_factory,
            adapter=adapter,
        )

        startup = StartupReconciliation(
            session_factory=session_factory,
            reconcile_service=reconcile_service,
        )

        result = await startup.run_startup_reconciliation()

        assert result is False

    @pytest.mark.asyncio
    async def test_submitting_projection_returns_false(self, session_factory) -> None:
        """SUBMITTING projection remains → return False."""
        _create_projection(session_factory, cid="cid-001", state=LedgerState.SUBMITTING)

        adapter = FakeReconcileAdapter()
        reconcile_service = OrderReconcileService(
            session_factory=session_factory,
            adapter=adapter,
        )

        startup = StartupReconciliation(
            session_factory=session_factory,
            reconcile_service=reconcile_service,
        )

        result = await startup.run_startup_reconciliation()

        assert result is False

    @pytest.mark.asyncio
    async def test_reconcile_error_returns_false(self, session_factory) -> None:
        """Reconcile error → return False (fail-closed)."""
        _create_projection(session_factory, cid="cid-001", state=LedgerState.UNKNOWN)

        adapter = FakeReconcileAdapter()
        # Make reconcile fail
        adapter.reconcile_result = None  # type: ignore

        reconcile_service = OrderReconcileService(
            session_factory=session_factory,
            adapter=adapter,
        )

        startup = StartupReconciliation(
            session_factory=session_factory,
            reconcile_service=reconcile_service,
        )

        result = await startup.run_startup_reconciliation()

        assert result is False
