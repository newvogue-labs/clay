"""Tests for D-12b-2: fills-reconcile (adapter, migration, repo, service)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Protocol, runtime_checkable

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
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
from clay.execution.adapter.errors import TransientAdapterError
from clay.execution.ledger.controller import OrderLedgerController
from clay.execution.ledger.reconcile import (
    OrderReconcileService,
    ReconcileAdapter,
    ReconcileMismatchKind,
)
from clay.execution.ledger.repository import OrderLedgerRepository
from clay.execution.ledger.states import LedgerState


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": SQLITE_SCHEMA_TRANSLATE_MAP},
    )


def _make_request(
    *, cid: str = "clay-test-001", symbol: str = "BTC/USDT"
) -> OrderRequest:
    return OrderRequest(
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.001"),
        time_in_force=TimeInForce.GTC,
        client_order_id=cid,
        price=Decimal("50000"),
    )


def _make_fill(
    *,
    trade_id: str = "t-001",
    venue_order_id: str = "v-ord-001",
    symbol: str = "BTC/USDT",
    quantity: Decimal = Decimal("0.0003"),
    transact_time: int = 1721395200000,
) -> Fill:
    return Fill(
        trade_id=trade_id,
        venue_order_id=venue_order_id,
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=quantity,
        price=Decimal("50000"),
        commission=Decimal("0.000001"),
        commission_asset="BTC",
        transact_time=transact_time,
    )


def _make_snapshot(
    *,
    client_order_id: str = "clay-test-001",
    venue_order_id: str = "v-ord-001",
    state: OrderState = OrderState.NEW,
) -> OrderSnapshot:
    return OrderSnapshot(
        client_order_id=client_order_id,
        venue_order_id=venue_order_id,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        state=state,
        quantity=Decimal("0.001"),
        executed_qty=Decimal("0"),
        price=Decimal("50000"),
        transact_time=1721395200000,
    )


class FakeClient:
    """Fake ccxt client for testing get_my_trades adapter method."""

    def __init__(self) -> None:
        self.my_trades_result: list[dict] = []
        self.error_to_raise: Exception | None = None

    async def fetch_my_trades(
        self, symbol: str = "", since: int | None = None, params: dict | None = None
    ) -> list[dict]:
        if self.error_to_raise:
            raise self.error_to_raise
        return self.my_trades_result


class FakeAdapter(ReconcileAdapter):
    """In-memory fake adapter for reconcile tests."""

    def __init__(self) -> None:
        self.reconcile_result: list[OrderSnapshot] = []
        self.open_result: list[OrderSnapshot] = []
        self.trades_result: list[Fill] = []
        self.trades_error: Exception | None = None

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]:
        return self.reconcile_result

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderSnapshot]:
        return self.open_result

    async def get_my_trades(
        self, symbol: str, *, since: datetime | None = None, from_id: str | None = None
    ) -> list[Fill]:
        if self.trades_error:
            raise self.trades_error
        return self.trades_result

    async def get_by_client_order_id(
        self, symbol: str, client_order_id: str
    ) -> OrderSnapshot | None:
        return None


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
# Adapter: get_my_trades
# ---------------------------------------------------------------------------


class TestGetMyTrades:
    @pytest.mark.asyncio()
    async def test_mapping_fee_fields(self) -> None:
        client = FakeClient()
        client.my_trades_result = [
            {
                "id": "trade-42",
                "order": "v-ord-001",
                "symbol": "BTC/USDT",
                "side": "sell",
                "amount": "0.0005",
                "price": "51000",
                "fee": {"cost": "0.000002", "currency": "BTC"},
                "timestamp": 1721395300000,
            }
        ]

        from clay.execution.adapter.ccxt_base import _fill_from_my_trade

        fill = _fill_from_my_trade(client.my_trades_result[0])
        assert fill.trade_id == "trade-42"
        assert fill.venue_order_id == "v-ord-001"
        assert fill.side == OrderSide.SELL
        assert fill.quantity == Decimal("0.0005")
        assert fill.commission == Decimal("0.000002")
        assert fill.commission_asset == "BTC"
        assert fill.transact_time == 1721395300000

    @pytest.mark.asyncio()
    async def test_order_none_guard(self) -> None:
        from clay.execution.adapter.ccxt_base import _fill_from_my_trade

        fill = _fill_from_my_trade({"id": "t-1", "order": None, "symbol": "X"})
        assert fill.venue_order_id == ""

    @pytest.mark.asyncio()
    async def test_from_id_param(self) -> None:
        adapter = FakeAdapter()
        adapter.trades_result = [_make_fill()]
        result = await adapter.get_my_trades("BTC/USDT", from_id="last-123")
        assert len(result) == 1

    @pytest.mark.asyncio()
    async def test_since_param(self) -> None:
        adapter = FakeAdapter()
        adapter.trades_result = [_make_fill()]
        result = await adapter.get_my_trades(
            "BTC/USDT", since=datetime(2026, 1, 1, tzinfo=UTC)
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Migration 0027
# ---------------------------------------------------------------------------

ALEMBIC_DIR = Path(__file__).resolve().parents[3] / "alembic"
MIGRATION_FILE = ALEMBIC_DIR / "versions" / "0027_reconcile_bookmark.py"


@runtime_checkable
class _MigrationModule(Protocol):
    def upgrade(self) -> None: ...
    def downgrade(self) -> None: ...


def _load_migration() -> _MigrationModule:
    spec = spec_from_file_location("migration_0027", MIGRATION_FILE)
    mod = module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod  # type: ignore[return-value]


class TestMigration0027:
    def _make_mig_engine(self) -> Engine:
        return create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            execution_options={"schema_translate_map": SQLITE_SCHEMA_TRANSLATE_MAP},
        )

    def test_upgrade_creates_table(self) -> None:
        eng = self._make_mig_engine()
        mod = _load_migration()
        with eng.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.upgrade()

            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            assert "reconcile_bookmark" in tables

            # Column check
            cols = {c["name"] for c in inspector.get_columns("reconcile_bookmark")}
            assert "bookmark_pk" in cols
            assert "venue" in cols
            assert "entity_type" in cols
            assert "symbol" in cols
            assert "last_trade_id" in cols
            assert "last_timestamp" in cols
            assert "updated_at" in cols

            # Unique constraint
            uqs = inspector.get_unique_constraints("reconcile_bookmark")
            assert any(
                u["column_names"] == ["venue", "entity_type", "symbol"] for u in uqs
            )
        eng.dispose()

    def test_roundtrip_upgrade_downgrade(self) -> None:
        eng = self._make_mig_engine()
        mod = _load_migration()
        with eng.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.upgrade()

            inspector = inspect(conn)
            assert "reconcile_bookmark" in set(inspector.get_table_names())

        with eng.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.downgrade()

            inspector = inspect(conn)
            assert "reconcile_bookmark" not in set(inspector.get_table_names())
        eng.dispose()


# ---------------------------------------------------------------------------
# Repo: bookmark get/upsert
# ---------------------------------------------------------------------------


class TestBookmarkRepo:
    def test_get_returns_none(self, sf: sessionmaker) -> None:  # type: ignore[type-arg]
        with sf() as s:
            repo = OrderLedgerRepository(s)
            bm = repo.get_reconcile_bookmark(
                venue="binance", entity_type="fills", symbol="BTC/USDT"
            )
            assert bm is None

    def test_upsert_insert_and_update(
        self,
        sf: sessionmaker,
        engine: Engine,  # type: ignore[type-arg]
    ) -> None:
        now = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)

        with sf() as s:
            repo = OrderLedgerRepository(s)
            repo.upsert_reconcile_bookmark(
                venue="binance",
                entity_type="fills",
                symbol="BTC/USDT",
                last_trade_id="t-001",
                last_timestamp=1721395200000,
                now=now,
            )
            s.commit()

        # Verify insert
        with sf() as s:
            repo = OrderLedgerRepository(s)
            bm = repo.get_reconcile_bookmark(
                venue="binance", entity_type="fills", symbol="BTC/USDT"
            )
            assert bm is not None
            assert bm.last_trade_id == "t-001"

        # Update
        now2 = datetime(2026, 7, 19, 13, 0, 0, tzinfo=UTC)
        with sf() as s:
            repo = OrderLedgerRepository(s)
            repo.upsert_reconcile_bookmark(
                venue="binance",
                entity_type="fills",
                symbol="BTC/USDT",
                last_trade_id="t-005",
                last_timestamp=1721395600000,
                now=now2,
            )
            s.commit()

        with sf() as s:
            repo = OrderLedgerRepository(s)
            bm = repo.get_reconcile_bookmark(
                venue="binance", entity_type="fills", symbol="BTC/USDT"
            )
            assert bm is not None
            assert bm.last_trade_id == "t-005"


# ---------------------------------------------------------------------------
# Service: fills reconcile
# ---------------------------------------------------------------------------


class TestFillsReconcile:
    def _setup_to_acknowledged(
        self, ctrl: OrderLedgerController, *, cid: str = "clay-test-001"
    ) -> None:
        req = _make_request(cid=cid)
        ctrl.record_intent(request=req, venue="binance")
        ctrl.apply_transition(
            client_order_id=cid, expected_version=0, to_state=LedgerState.SUBMITTING
        )
        ctrl.apply_transition(
            client_order_id=cid, expected_version=1, to_state=LedgerState.ACKNOWLEDGED
        )

    # (a) heal ACK→PF with fills → filled_qty recalculated
    @pytest.mark.asyncio()
    async def test_heal_with_fills(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
    ) -> None:
        self._setup_to_acknowledged(ctrl)
        adapter.reconcile_result = [_make_snapshot(state=OrderState.PARTIALLY_FILLED)]
        adapter.trades_result = [
            _make_fill(trade_id="t-001", quantity=Decimal("0.0003"))
        ]

        report = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        assert "clay-test-001" in report.healed
        with ctrl._session_factory() as s:
            repo = OrderLedgerRepository(s)
            proj = repo.get_projection("clay-test-001")
            assert proj is not None
            assert proj.filled_qty == "0.0003"
            assert proj.lifecycle_state == LedgerState.PARTIALLY_FILLED

    # (b) heal→FILLED with fills
    @pytest.mark.asyncio()
    async def test_heal_to_filled_with_fills(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
    ) -> None:
        self._setup_to_acknowledged(ctrl)
        adapter.reconcile_result = [_make_snapshot(state=OrderState.FILLED)]
        adapter.trades_result = [
            _make_fill(trade_id="t-001", quantity=Decimal("0.001"))
        ]

        report = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        assert "clay-test-001" in report.healed
        with ctrl._session_factory() as s:
            repo = OrderLedgerRepository(s)
            proj = repo.get_projection("clay-test-001")
            assert proj is not None
            assert proj.lifecycle_state == LedgerState.FILLED
            assert proj.filled_qty == "0.001"

    # (c) idempotent: dedup, version stable, filled_qty not doubled
    @pytest.mark.asyncio()
    async def test_idempotent(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
    ) -> None:
        self._setup_to_acknowledged(ctrl)
        adapter.reconcile_result = [_make_snapshot(state=OrderState.PARTIALLY_FILLED)]
        adapter.trades_result = [
            _make_fill(trade_id="t-001", quantity=Decimal("0.0003"))
        ]

        r1 = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )
        assert len(r1.healed) == 1

        r2 = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )
        assert len(r2.healed) == 0  # no-op, already PARTIALLY_FILLED

        with ctrl._session_factory() as s:
            repo = OrderLedgerRepository(s)
            proj = repo.get_projection("clay-test-001")
            assert proj is not None
            assert proj.filled_qty == "0.0003"  # not doubled

    # (d) orphan fill → LEDGER_ORPHAN
    @pytest.mark.asyncio()
    async def test_orphan_fill(
        self, svc: OrderReconcileService, adapter: FakeAdapter
    ) -> None:
        adapter.reconcile_result = []
        adapter.trades_result = [
            _make_fill(venue_order_id="unknown-void", trade_id="t-999")
        ]

        report = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        orphans = [
            m
            for m in report.mismatches
            if m.kind == ReconcileMismatchKind.LEDGER_ORPHAN
        ]
        assert any("unknown-void" in m.detail for m in orphans)

    # (e) bookmark advances after success
    @pytest.mark.asyncio()
    async def test_bookmark_advances(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
        sf: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        self._setup_to_acknowledged(ctrl)
        adapter.reconcile_result = [_make_snapshot(state=OrderState.PARTIALLY_FILLED)]
        adapter.trades_result = [
            _make_fill(trade_id="t-005", transact_time=1721396000000)
        ]

        await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        with sf() as s:
            repo = OrderLedgerRepository(s)
            bm = repo.get_reconcile_bookmark(
                venue="binance", entity_type="fills", symbol="BTC/USDT"
            )
            assert bm is not None
            assert bm.last_trade_id == "t-005"
            assert bm.last_timestamp == 1721396000000

    # (f) error in get_my_trades → bookmark not advanced (fail-closed)
    @pytest.mark.asyncio()
    async def test_fail_closed_bookmark(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
        sf: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        self._setup_to_acknowledged(ctrl)
        adapter.reconcile_result = [_make_snapshot(state=OrderState.PARTIALLY_FILLED)]
        adapter.trades_error = TransientAdapterError("network down")

        with pytest.raises(TransientAdapterError):
            await svc.reconcile_symbol(
                "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
            )

        with sf() as s:
            repo = OrderLedgerRepository(s)
            bm = repo.get_reconcile_bookmark(
                venue="binance", entity_type="fills", symbol="BTC/USDT"
            )
            assert bm is None  # not advanced

    # (g) no-op when no new trades
    @pytest.mark.asyncio()
    async def test_noop_no_trades(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
    ) -> None:
        self._setup_to_acknowledged(ctrl)
        adapter.reconcile_result = [_make_snapshot(state=OrderState.NEW)]
        adapter.trades_result = []

        report = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        assert len(report.healed) == 0
        with ctrl._session_factory() as s:
            repo = OrderLedgerRepository(s)
            proj = repo.get_projection("clay-test-001")
            assert proj is not None
            assert proj.version == 2  # unchanged from acknowledged

    # D-12c: bookmark advances only to max-ingested fill
    @pytest.mark.asyncio()
    async def test_bookmark_advances_to_max_ingested(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
        sf: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """When fills_raw has fills for multiple orders, but only some
        are ingested (matched to projections), bookmark advances only
        to the max ingested fill, not max fills_raw."""
        self._setup_to_acknowledged(ctrl, cid="clay-test-001")
        adapter.reconcile_result = [_make_snapshot(state=OrderState.PARTIALLY_FILLED)]

        # Two fills: one for the known order, one orphan
        adapter.trades_result = [
            _make_fill(
                trade_id="t-ingested",
                venue_order_id="v-ord-001",
                transact_time=1721396000000,  # earlier
            ),
            _make_fill(
                trade_id="t-orphan",
                venue_order_id="v-orphan-999",
                transact_time=1721397000000,  # later, but orphan
            ),
        ]

        await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        # Bookmark should be at the ingested fill, not the orphan
        with sf() as s:
            repo = OrderLedgerRepository(s)
            bm = repo.get_reconcile_bookmark(
                venue="binance", entity_type="fills", symbol="BTC/USDT"
            )
            assert bm is not None
            assert bm.last_trade_id == "t-ingested"
            assert bm.last_timestamp == 1721396000000

    # D-12c: orphan-only fills → bookmark NOT advanced + signal
    @pytest.mark.asyncio()
    async def test_bookmark_not_advanced_on_orphan_only(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
        sf: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """When fills_raw has only orphan fills (no projection match),
        bookmark is NOT advanced and a signal mismatch is added."""
        self._setup_to_acknowledged(ctrl, cid="clay-test-001")
        # No venue state to heal → no record_fills called
        adapter.reconcile_result = [_make_snapshot(state=OrderState.NEW)]

        # Only orphan fills
        adapter.trades_result = [
            _make_fill(
                trade_id="t-orphan-1",
                venue_order_id="v-orphan-999",
                transact_time=1721397000000,
            ),
        ]

        report = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        # Bookmark should NOT be advanced
        with sf() as s:
            repo = OrderLedgerRepository(s)
            bm = repo.get_reconcile_bookmark(
                venue="binance", entity_type="fills", symbol="BTC/USDT"
            )
            assert bm is None

        # Signal mismatch present
        signal = [m for m in report.mismatches if "cursor_not_advanced" in m.detail]
        assert len(signal) == 1

    # D-12c: repeat run re-fetches orphan fills
    @pytest.mark.asyncio()
    async def test_repeat_run_refetches_orphans(
        self,
        svc: OrderReconcileService,
        ctrl: OrderLedgerController,
        adapter: FakeAdapter,
        sf: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """After orphan-only run (bookmark not advanced), next run
        re-fetches the same fills from the venue."""
        self._setup_to_acknowledged(ctrl, cid="clay-test-001")
        adapter.reconcile_result = [_make_snapshot(state=OrderState.NEW)]

        # First run: orphan fills
        adapter.trades_result = [
            _make_fill(
                trade_id="t-orphan-1",
                venue_order_id="v-orphan-999",
                transact_time=1721397000000,
            ),
        ]
        await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        # Second run: same orphan fills (bookmark not advanced, so from_id=None)
        adapter.trades_result = [
            _make_fill(
                trade_id="t-orphan-1",
                venue_order_id="v-orphan-999",
                transact_time=1721397000000,
            ),
        ]
        report2 = await svc.reconcile_symbol(
            "BTC/USDT", datetime(2026, 1, 1, tzinfo=UTC), venue="binance"
        )

        # Should still see the orphan signal (not skipped by bookmark)
        signal = [m for m in report2.mismatches if "cursor_not_advanced" in m.detail]
        assert len(signal) == 1
