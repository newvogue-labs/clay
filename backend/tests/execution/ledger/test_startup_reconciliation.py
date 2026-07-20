"""Tests for D-12d D2: startup-reconciliation before execution-gate."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

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


# === D-15: fatal_halt_wiring integration ===


class TestStartupReconciliationFatalWiring:
    """D-15: StartupReconciliation wires fatal reports to halt-latch."""

    @pytest.mark.asyncio
    async def test_fatal_engages_latch(self, session_factory) -> None:
        """Fatal report → halt-latch engaged via wiring."""
        from clay.execution.ledger.fatal_halt import FatalHaltWiring
        from clay.execution.ledger.halt_latch import HaltLatchRepository

        _create_projection(session_factory, cid="cid-001", state=LedgerState.UNKNOWN)

        # Adapter that returns a fatal report
        adapter = FakeReconcileAdapter()
        reconcile_service = OrderReconcileService(
            session_factory=session_factory,
            adapter=adapter,
        )

        wiring = FatalHaltWiring(session_factory=session_factory)

        startup = StartupReconciliation(
            session_factory=session_factory,
            reconcile_service=reconcile_service,
            fatal_halt_wiring=wiring,
        )

        # Make reconcile_symbol return a fatal report
        from clay.execution.ledger.reconcile import (
            Mismatch,
            ReconcileMismatchKind,
            ReconcileReport,
        )

        fatal_report = ReconcileReport(
            mismatches=[
                Mismatch(
                    kind=ReconcileMismatchKind.ILLEGAL_DRIFT,
                    client_order_id="cid-001",
                    venue_order_id="void-001",
                    detail="test fatal",
                )
            ]
        )

        async def _fatal_reconcile(
            symbol: str, since: datetime, *, venue: str
        ) -> ReconcileReport:
            return fatal_report

        reconcile_service.reconcile_symbol = _fatal_reconcile  # type: ignore[method-assign]

        result = await startup.run_startup_reconciliation()

        # Latch should be engaged
        with session_factory() as s:
            repo = HaltLatchRepository(s)
            assert repo.is_engaged() is True

        # Return False because has_fatal
        assert result is False

    @pytest.mark.asyncio
    async def test_escalated_engages_latch(self, session_factory) -> None:
        """Age-escalated UNKNOWNs → halt-latch engaged via wiring."""
        from unittest.mock import AsyncMock, MagicMock as MockMagic

        from clay.execution.ledger.fatal_halt import FatalHaltWiring
        from clay.execution.ledger.halt_latch import HaltLatchRepository

        _create_projection(session_factory, cid="cid-001", state=LedgerState.UNKNOWN)

        adapter = FakeReconcileAdapter()
        reconcile_service = OrderReconcileService(
            session_factory=session_factory,
            adapter=adapter,
        )

        wiring = FatalHaltWiring(session_factory=session_factory)

        # Create a mock unknown_resolver that returns escalated (async method)
        mock_resolver = MockMagic()
        resolver_report = MockMagic()
        resolver_report.escalated_to_fatal = ["cid-001"]
        mock_resolver.resolve_symbol = AsyncMock(return_value=resolver_report)

        startup = StartupReconciliation(
            session_factory=session_factory,
            reconcile_service=reconcile_service,
            unknown_resolver=mock_resolver,
            fatal_halt_wiring=wiring,
        )

        result = await startup.run_startup_reconciliation()

        # Latch should be engaged
        with session_factory() as s:
            repo = HaltLatchRepository(s)
            assert repo.is_engaged() is True

        # Return False because escalated_to_fatal
        assert result is False

    @pytest.mark.asyncio
    async def test_wiring_none_no_crash(self, session_factory) -> None:
        """fatal_halt_wiring=None → no crash on fatal report."""
        _create_projection(session_factory, cid="cid-001", state=LedgerState.UNKNOWN)

        adapter = FakeReconcileAdapter()
        reconcile_service = OrderReconcileService(
            session_factory=session_factory,
            adapter=adapter,
        )

        startup = StartupReconciliation(
            session_factory=session_factory,
            reconcile_service=reconcile_service,
            # fatal_halt_wiring=None (default)
        )

        # reconcile will fail (adapter returns None type) → returns False
        result = await startup.run_startup_reconciliation()
        assert result is False
