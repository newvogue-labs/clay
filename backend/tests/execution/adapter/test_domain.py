"""Tests for adapter domain DTOs — frozen / Decimal / immutability."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from clay.execution.adapter.domain import (
    BalanceSnapshot,
    Fill,
    OrderAck,
    OrderRequest,
    OrderSnapshot,
)
from clay.execution.adapter.enums import OrderSide, OrderState, OrderType, TimeInForce


# ---------------------------------------------------------------------------
# OrderRequest
# ---------------------------------------------------------------------------


class TestOrderRequest:
    def test_frozen(self) -> None:
        req = _make_request()
        with pytest.raises(FrozenInstanceError):
            req.quantity = Decimal("999")  # type: ignore[misc]

    def test_decimal_fields(self) -> None:
        req = _make_request()
        assert isinstance(req.quantity, Decimal)
        assert isinstance(req.price, Decimal)
        assert req.stop_price is None

    def test_price_optional(self) -> None:
        req = _make_request(price=None)
        assert req.price is None

    def test_eq(self) -> None:
        a = _make_request()
        b = _make_request()
        assert a == b

    def test_hash(self) -> None:
        req = _make_request()
        assert hash(req) == hash(_make_request())


# ---------------------------------------------------------------------------
# Fill
# ---------------------------------------------------------------------------


class TestFill:
    def test_frozen(self) -> None:
        fill = _make_fill()
        with pytest.raises(FrozenInstanceError):
            fill.price = Decimal("0")  # type: ignore[misc]

    def test_decimal_fields(self) -> None:
        fill = _make_fill()
        for attr in ("quantity", "price", "commission"):
            assert isinstance(getattr(fill, attr), Decimal)


# ---------------------------------------------------------------------------
# OrderAck
# ---------------------------------------------------------------------------


class TestOrderAck:
    def test_frozen(self) -> None:
        ack = _make_ack()
        with pytest.raises(FrozenInstanceError):
            ack.state = OrderState.FILLED  # type: ignore[misc]

    def test_empty_fills_default(self) -> None:
        ack = _make_ack()
        assert ack.fills == ()

    def test_tuple_fills(self) -> None:
        ack = _make_ack(fills=(_make_fill(),))
        assert isinstance(ack.fills, tuple)
        assert len(ack.fills) == 1


# ---------------------------------------------------------------------------
# OrderSnapshot
# ---------------------------------------------------------------------------


class TestOrderSnapshot:
    def test_frozen(self) -> None:
        snap = _make_snapshot()
        with pytest.raises(FrozenInstanceError):
            snap.executed_qty = Decimal("0")  # type: ignore[misc]

    def test_decimal_fields(self) -> None:
        snap = _make_snapshot()
        assert isinstance(snap.executed_qty, Decimal)
        assert isinstance(snap.quantity, Decimal)


# ---------------------------------------------------------------------------
# BalanceSnapshot
# ---------------------------------------------------------------------------


class TestBalanceSnapshot:
    def test_frozen(self) -> None:
        bal = BalanceSnapshot(
            asset="USDT",
            free=Decimal("1000"),
            locked=Decimal("50"),
            total=Decimal("1050"),
        )
        with pytest.raises(FrozenInstanceError):
            bal.free = Decimal("0")  # type: ignore[misc]

    def test_decimal_fields(self) -> None:
        bal = BalanceSnapshot(
            asset="BTC",
            free=Decimal("1.5"),
            locked=Decimal("0"),
            total=Decimal("1.5"),
        )
        for attr in ("free", "locked", "total"):
            assert isinstance(getattr(bal, attr), Decimal)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_request(
    *,
    price: Decimal | None = Decimal("50000"),
    stop_price: Decimal | None = None,
) -> OrderRequest:
    return OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=price,
        stop_price=stop_price,
        time_in_force=TimeInForce.GTC,
        client_order_id="test-001",
    )


def _make_fill() -> Fill:
    return Fill(
        trade_id="t-1",
        venue_order_id="v-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.01"),
        price=Decimal("50000"),
        commission=Decimal("0.5"),
        commission_asset="USDT",
        transact_time=1700000000000,
    )


def _make_ack(*, fills: tuple[Fill, ...] = ()) -> OrderAck:
    return OrderAck(
        client_order_id="test-001",
        venue_order_id="v-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        state=OrderState.NEW,
        quantity=Decimal("0.01"),
        price=Decimal("50000"),
        transact_time=1700000000000,
        fills=fills,
    )


def _make_snapshot() -> OrderSnapshot:
    return OrderSnapshot(
        client_order_id="test-001",
        venue_order_id="v-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        state=OrderState.NEW,
        quantity=Decimal("0.01"),
        executed_qty=Decimal("0"),
        price=Decimal("50000"),
        transact_time=1700000000000,
    )
