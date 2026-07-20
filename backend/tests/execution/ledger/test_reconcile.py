"""Tests for OrderReconcileService — venue-state reconciliation."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from clay.db import models_orders  # noqa: F401 — register tables
from clay.db.base import Base
from clay.db.session import SQLITE_SCHEMA_TRANSLATE_MAP
from clay.execution.adapter.domain import Fill, OrderRequest, OrderSnapshot
from clay.execution.adapter.enums import (
    OrderSide,
    OrderState,
    OrderType,
    TimeInForce,
)
from clay.execution.ledger.controller import OrderLedgerController
from clay.execution.ledger.reconcile import (
    ReconcileAdapter,
    ReconcileMismatchKind,
    OrderReconcileService,
    map_venue_state,
)
from clay.execution.ledger.states import LedgerState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": SQLITE_SCHEMA_TRANSLATE_MAP},
    )


def _make_request(
    *,
    client_order_id: str = "clay-test-001",
    symbol: str = "BTC/USDT",
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.LIMIT,
    quantity: Decimal = Decimal("0.001"),
    price: Decimal = Decimal("50000"),
    time_in_force: TimeInForce = TimeInForce.GTC,
) -> OrderRequest:
    return OrderRequest(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        time_in_force=time_in_force,
        client_order_id=client_order_id,
        price=price,
    )


def _make_snapshot(
    *,
    client_order_id: str = "clay-test-001",
    venue_order_id: str = "v-ord-001",
    symbol: str = "BTC/USDT",
    state: OrderState = OrderState.NEW,
) -> OrderSnapshot:
    return OrderSnapshot(
        client_order_id=client_order_id,
        venue_order_id=venue_order_id,
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        state=state,
        quantity=Decimal("0.001"),
        executed_qty=Decimal("0"),
        price=Decimal("50000"),
        transact_time=1721395200000,
    )


class FakeAdapter(ReconcileAdapter):
    """In-memory fake adapter for tests."""

    def __init__(self) -> None:
        self.reconcile_result: list[OrderSnapshot] = []
        self.open_result: list[OrderSnapshot] = []
        self.trades_result: list[Fill] = []

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]:
        return self.reconcile_result

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderSnapshot]:
        return self.open_result

    async def get_my_trades(
        self, symbol: str, *, since: datetime | None = None, from_id: str | None = None
    ) -> list[Fill]:
        return self.trades_result


@pytest.fixture()
def engine() -> Generator[Engine, None, None]:
    eng = _make_engine()
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def sf(engine: Engine) -> sessionmaker:  # type: ignore[type-arg]
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


@pytest.fixture()
def ctrl(sf: sessionmaker) -> OrderLedgerController:  # type: ignore[type-arg]
    fixed_now = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
    return OrderLedgerController(sf, now_fn=lambda: fixed_now)


@pytest.fixture()
def adapter() -> FakeAdapter:
    return FakeAdapter()


@pytest.fixture()
def svc(
    sf: sessionmaker,
    adapter: FakeAdapter,  # type: ignore[type-arg]
) -> OrderReconcileService:
    fixed_now = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
    return OrderReconcileService(sf, adapter, now_fn=lambda: fixed_now)


# ---------------------------------------------------------------------------
# D2: unit map_venue_state
# ---------------------------------------------------------------------------


class TestMapVenueState:
    def test_new_to_acknowledged(self) -> None:
        assert map_venue_state(OrderState.NEW) == LedgerState.ACKNOWLEDGED

    def test_partially_filled(self) -> None:
        assert (
            map_venue_state(OrderState.PARTIALLY_FILLED) == LedgerState.PARTIALLY_FILLED
        )

    def test_filled(self) -> None:
        assert map_venue_state(OrderState.FILLED) == LedgerState.FILLED

    def test_canceled(self) -> None:
        assert map_venue_state(OrderState.CANCELED) == LedgerState.CANCELED

    def test_rejected(self) -> None:
        assert map_venue_state(OrderState.REJECTED) == LedgerState.REJECTED

    def test_expired(self) -> None:
        assert map_venue_state(OrderState.EXPIRED) == LedgerState.EXPIRED


# ---------------------------------------------------------------------------
# D4: reconcile_symbol
# ---------------------------------------------------------------------------


class TestReconcileSymbol:
    """7 test cases from D-12b-1 spec."""

    def _setup_to_acknowledged(
        self, ctrl: OrderLedgerController, *, cid: str = "clay-test-001"
    ) -> None:
        """intent → submitting → acknowledged."""
        req = _make_request(client_order_id=cid)
        ctrl.record_intent(request=req, venue="binance")
        ctrl.apply_transition(
            client_order_id=cid, expected_version=0, to_state=LedgerState.SUBMITTING
        )
        ctrl.apply_transition(
            client_order_id=cid, expected_version=1, to_state=LedgerState.ACKNOWLEDGED
        )

    # 1. heal ACKNOWLEDGED -> PARTIALLY_FILLED
    @pytest.mark.asyncio()
    async def test_heal_acknowledged_to_partially_filled(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
        engine: Engine,
    ) -> None:
        self._setup_to_acknowledged(ctrl)

        adapter.reconcile_result = [_make_snapshot(state=OrderState.PARTIALLY_FILLED)]

        report = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        assert "clay-test-001" in report.healed
        assert not report.has_fatal

        # version incremented
        with ctrl._session_factory() as s:
            from clay.execution.ledger.repository import OrderLedgerRepository

            repo = OrderLedgerRepository(s)
            proj = repo.get_projection("clay-test-001")
            assert proj is not None
            assert proj.version == 3  # was 2 after acknowledged

    # 2. idempotency: second run → 0 heals
    @pytest.mark.asyncio()
    async def test_idempotent(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
    ) -> None:
        self._setup_to_acknowledged(ctrl)

        adapter.reconcile_result = [_make_snapshot(state=OrderState.PARTIALLY_FILLED)]

        report1 = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )
        assert len(report1.healed) == 1

        # Second run — same venue state, already PARTIALLY_FILLED
        report2 = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )
        assert len(report2.healed) == 0

    # 3. ILLEGAL_DRIFT: INTENT + venue filled → 0 mutations, has_fatal True
    @pytest.mark.asyncio()
    async def test_illegal_drift(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
        engine: Engine,
    ) -> None:
        req = _make_request()
        ctrl.record_intent(request=req, venue="binance")
        # Projection is still INTENT (version=0)

        adapter.reconcile_result = [_make_snapshot(state=OrderState.FILLED)]

        report = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        assert report.has_fatal
        illegal = [
            m
            for m in report.mismatches
            if m.kind == ReconcileMismatchKind.ILLEGAL_DRIFT
        ]
        assert len(illegal) == 1
        assert illegal[0].client_order_id == "clay-test-001"

        # No mutations: version unchanged, no new events
        with ctrl._session_factory() as s:
            from clay.execution.ledger.repository import OrderLedgerRepository

            repo = OrderLedgerRepository(s)
            proj = repo.get_projection("clay-test-001")
            assert proj is not None
            assert proj.version == 0

        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM order_events")).scalar()
            assert count == 1  # only the INTENT event

    # 4. VENUE_ORPHAN: venue order without projection
    @pytest.mark.asyncio()
    async def test_venue_orphan(
        self,
        svc: OrderReconcileService,
        adapter: FakeAdapter,
    ) -> None:
        adapter.reconcile_result = [
            _make_snapshot(
                client_order_id="unknown-cid",
                venue_order_id="v-ord-999",
                state=OrderState.NEW,
            )
        ]

        report = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        assert report.has_fatal
        orphans = [
            m for m in report.mismatches if m.kind == ReconcileMismatchKind.VENUE_ORPHAN
        ]
        assert len(orphans) == 1
        assert orphans[0].venue_order_id == "v-ord-999"

    # 5. LEDGER_ORPHAN: active projection not in venue
    @pytest.mark.asyncio()
    async def test_ledger_orphan(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
    ) -> None:
        self._setup_to_acknowledged(ctrl)

        # Venue returns empty — no orders
        adapter.reconcile_result = []

        report = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        assert not report.has_fatal
        orphans = [
            m
            for m in report.mismatches
            if m.kind == ReconcileMismatchKind.LEDGER_ORPHAN
        ]
        assert len(orphans) == 1
        assert orphans[0].client_order_id == "clay-test-001"

    # 6. FSM-respecting: IllegalTransitionError caught and classified
    @pytest.mark.asyncio()
    async def test_fsm_respecting(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
    ) -> None:
        # INTENT projection — INTENT -> FILLED is illegal in FSM
        req = _make_request()
        ctrl.record_intent(request=req, venue="binance")

        adapter.reconcile_result = [_make_snapshot(state=OrderState.FILLED)]

        report = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        # ILLEGAL_DRIFT, not a raised exception
        assert report.has_fatal
        illegal = [
            m
            for m in report.mismatches
            if m.kind == ReconcileMismatchKind.ILLEGAL_DRIFT
        ]
        assert len(illegal) == 1
        assert "illegal" in illegal[0].detail

    # 7. STATE_DRIFT heal: ACKNOWLEDGED → FILLED
    @pytest.mark.asyncio()
    async def test_heal_state_drift_to_filled(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
    ) -> None:
        self._setup_to_acknowledged(ctrl)

        adapter.reconcile_result = [_make_snapshot(state=OrderState.FILLED)]

        report = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        assert "clay-test-001" in report.healed
        assert not report.has_fatal

        with ctrl._session_factory() as s:
            from clay.execution.ledger.repository import OrderLedgerRepository

            repo = OrderLedgerRepository(s)
            proj = repo.get_projection("clay-test-001")
            assert proj is not None
            assert proj.lifecycle_state == LedgerState.FILLED
