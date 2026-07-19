"""Tests for OrderLedgerController — record_intent + apply_transition."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from clay.db import models_orders  # noqa: F401 — register tables in Base.metadata
from clay.db.base import Base
from clay.db.session import SQLITE_SCHEMA_TRANSLATE_MAP
from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import OrderSide, OrderType, TimeInForce
from clay.execution.ledger.controller import OrderLedgerController
from clay.execution.ledger.errors import (
    ConcurrencyConflictError,
    DuplicateOrderIntentError,
    IllegalTransitionError,
    OrderNotInLedgerError,
)
from clay.execution.ledger.states import LedgerState
from clay.execution.proof.checker import semantic_intent_hash


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


# ---------------------------------------------------------------------------
# record_intent
# ---------------------------------------------------------------------------


class TestRecordIntent:
    def test_creates_event_and_projection(
        self, ctrl: OrderLedgerController, engine: Engine
    ) -> None:
        req = _make_request()
        proj = ctrl.record_intent(request=req, venue="binance")

        assert proj.client_order_id == "clay-test-001"
        assert proj.lifecycle_state == LedgerState.INTENT
        assert proj.version == 0
        assert proj.venue == "binance"
        assert proj.symbol == "BTC/USDT"
        assert proj.filled_qty == "0"

        # Проверяем событие в БД
        with engine.connect() as conn:
            from sqlalchemy import text

            rows = conn.execute(
                text("SELECT event_id, event_type FROM order_events")
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][1] == "intent"

    def test_last_event_id_matches_event(self, ctrl: OrderLedgerController) -> None:
        from sqlalchemy import select

        from clay.db.models_orders import OrderEvent

        req = _make_request()
        proj = ctrl.record_intent(request=req, venue="binance")

        with ctrl._session_factory() as s:
            ev = s.scalars(
                select(OrderEvent).where(OrderEvent.event_id == proj.last_event_id)
            ).one()
            assert ev.client_order_id == "clay-test-001"

    def test_duplicate_cid_raises(
        self, ctrl: OrderLedgerController, engine: Engine
    ) -> None:
        req = _make_request()
        ctrl.record_intent(request=req, venue="binance")

        with pytest.raises(DuplicateOrderIntentError):
            ctrl.record_intent(request=req, venue="binance")

        # В БД ровно 1 событие и 1 проекция (откат)
        with engine.connect() as conn:
            from sqlalchemy import text

            events = conn.execute(text("SELECT COUNT(*) FROM order_events")).scalar()
            projs = conn.execute(
                text("SELECT COUNT(*) FROM order_current_state")
            ).scalar()
            assert events == 1
            assert projs == 1


# ---------------------------------------------------------------------------
# apply_transition
# ---------------------------------------------------------------------------


class TestApplyTransition:
    def _setup_intent(
        self, ctrl: OrderLedgerController, *, cid: str = "clay-test-001"
    ) -> None:
        req = _make_request(client_order_id=cid)
        ctrl.record_intent(request=req, venue="binance")

    def test_legal_transition_intent_to_submitting(
        self, ctrl: OrderLedgerController
    ) -> None:
        self._setup_intent(ctrl)

        proj = ctrl.apply_transition(
            client_order_id="clay-test-001",
            expected_version=0,
            to_state=LedgerState.SUBMITTING,
        )
        assert proj.lifecycle_state == LedgerState.SUBMITTING
        assert proj.version == 1

    def test_version_increments(self, ctrl: OrderLedgerController) -> None:
        self._setup_intent(ctrl)

        ctrl.apply_transition(
            client_order_id="clay-test-001",
            expected_version=0,
            to_state=LedgerState.SUBMITTING,
        )
        proj = ctrl.apply_transition(
            client_order_id="clay-test-001",
            expected_version=1,
            to_state=LedgerState.ACKNOWLEDGED,
        )
        assert proj.version == 2
        assert proj.lifecycle_state == LedgerState.ACKNOWLEDGED

    def test_event_appended_on_transition(
        self, ctrl: OrderLedgerController, engine: Engine
    ) -> None:
        self._setup_intent(ctrl)

        ctrl.apply_transition(
            client_order_id="clay-test-001",
            expected_version=0,
            to_state=LedgerState.SUBMITTING,
        )

        with engine.connect() as conn:
            from sqlalchemy import text

            rows = conn.execute(
                text("SELECT event_type FROM order_events ORDER BY ledger_seq")
            ).fetchall()
            assert len(rows) == 2
            assert rows[0][0] == "intent"
            assert rows[1][0] == "submitting"

    def test_last_event_id_updated(self, ctrl: OrderLedgerController) -> None:
        self._setup_intent(ctrl)

        proj = ctrl.apply_transition(
            client_order_id="clay-test-001",
            expected_version=0,
            to_state=LedgerState.SUBMITTING,
        )
        assert proj.last_event_id != ""

    def test_wrong_version_raises(
        self, ctrl: OrderLedgerController, engine: Engine
    ) -> None:
        self._setup_intent(ctrl)

        with pytest.raises(ConcurrencyConflictError):
            ctrl.apply_transition(
                client_order_id="clay-test-001",
                expected_version=99,
                to_state=LedgerState.SUBMITTING,
            )

        # Проекция без изменений
        with ctrl._session_factory() as s:
            from clay.execution.ledger.repository import OrderLedgerRepository

            repo = OrderLedgerRepository(s)
            proj = repo.get_projection("clay-test-001")
            assert proj is not None
            assert proj.version == 0

        # Нового события НЕТ (откат)
        with engine.connect() as conn:
            from sqlalchemy import text

            count = conn.execute(text("SELECT COUNT(*) FROM order_events")).scalar()
            assert count == 1

    def test_illegal_transition_raises(self, ctrl: OrderLedgerController) -> None:
        self._setup_intent(ctrl)
        # INTENT -> FILLED — нелегально
        with pytest.raises(IllegalTransitionError) as exc_info:
            ctrl.apply_transition(
                client_order_id="clay-test-001",
                expected_version=0,
                to_state=LedgerState.FILLED,
            )
        assert exc_info.value.from_state == LedgerState.INTENT
        assert exc_info.value.to_state == LedgerState.FILLED

    def test_nonexistent_cid_raises(self, ctrl: OrderLedgerController) -> None:
        with pytest.raises(OrderNotInLedgerError):
            ctrl.apply_transition(
                client_order_id="does-not-exist",
                expected_version=0,
                to_state=LedgerState.SUBMITTING,
            )

    def test_partial_fill_self_transition(self, ctrl: OrderLedgerController) -> None:
        self._setup_intent(ctrl)

        ctrl.apply_transition(
            client_order_id="clay-test-001",
            expected_version=0,
            to_state=LedgerState.SUBMITTING,
        )
        ctrl.apply_transition(
            client_order_id="clay-test-001",
            expected_version=1,
            to_state=LedgerState.ACKNOWLEDGED,
        )
        proj = ctrl.apply_transition(
            client_order_id="clay-test-001",
            expected_version=2,
            to_state=LedgerState.PARTIALLY_FILLED,
            filled_qty="0.0005",
        )
        assert proj.filled_qty == "0.0005"
        assert proj.lifecycle_state == LedgerState.PARTIALLY_FILLED

        # Self-transition: PARTIALLY_FILLED -> PARTIALLY_FILLED
        proj2 = ctrl.apply_transition(
            client_order_id="clay-test-001",
            expected_version=3,
            to_state=LedgerState.PARTIALLY_FILLED,
            filled_qty="0.0008",
        )
        assert proj2.filled_qty == "0.0008"
        assert proj2.version == 4


# ---------------------------------------------------------------------------
# semantic_hash
# ---------------------------------------------------------------------------


class TestSemanticHash:
    def test_hash_matches_semantic_intent_hash(
        self, ctrl: OrderLedgerController
    ) -> None:
        req = _make_request()
        proj = ctrl.record_intent(request=req, venue="binance")

        expected = semantic_intent_hash(req)
        assert proj.semantic_hash == expected

    def test_same_hash_different_cid(self, ctrl: OrderLedgerController) -> None:
        """Два запроса, отличающиеся ТОЛЬКО client_order_id, дают одинаковый hash."""
        req1 = _make_request(client_order_id="cid-aaa")
        req2 = _make_request(client_order_id="cid-bbb")

        proj1 = ctrl.record_intent(request=req1, venue="binance")
        proj2 = ctrl.record_intent(request=req2, venue="binance")

        assert proj1.semantic_hash == proj2.semantic_hash
        assert proj1.semantic_hash == semantic_intent_hash(req1)

    def test_hash_in_event_payload(self, ctrl: OrderLedgerController) -> None:
        from sqlalchemy import select

        from clay.db.models_orders import OrderEvent

        req = _make_request()
        proj = ctrl.record_intent(request=req, venue="binance")

        with ctrl._session_factory() as s:
            ev = s.scalars(
                select(OrderEvent).where(OrderEvent.event_id == proj.last_event_id)
            ).one()
            assert ev.semantic_hash == semantic_intent_hash(req)
