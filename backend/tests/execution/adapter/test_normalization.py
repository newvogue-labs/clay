"""Tests for adapter normalization — validate_order + quantize_order."""

from __future__ import annotations

from decimal import Decimal

import pytest

from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import (
    OrderSide,
    OrderType,
    PrecisionMode,
    TimeInForce,
)
from clay.execution.adapter.errors import InvalidOrderError
from clay.execution.adapter.normalization import quantize_order, validate_order
from clay.execution.adapter.rules import MarketRules


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _default_rules(**overrides: object) -> MarketRules:
    defaults: dict[str, object] = {
        "min_amount": Decimal("0.001"),
        "max_amount": Decimal("1000"),
        "min_price": Decimal("0.01"),
        "max_price": Decimal("1000000"),
        "min_notional": Decimal("10"),
        "amount_step": Decimal("0.001"),
        "price_tick": Decimal("0.01"),
        "precision_mode": PrecisionMode.TICK_SIZE,
        "supported_order_types": frozenset(
            {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT}
        ),
        "supported_tif": frozenset({TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK}),
    }
    defaults.update(overrides)
    return MarketRules(**defaults)  # type: ignore[arg-type]


def _make_request(
    *,
    quantity: str = "0.01",
    price: str | None = "50000",
    stop_price: str | None = None,
    order_type: OrderType = OrderType.LIMIT,
    time_in_force: TimeInForce = TimeInForce.GTC,
) -> OrderRequest:
    return OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=order_type,
        quantity=Decimal(quantity),
        price=Decimal(price) if price is not None else None,
        stop_price=Decimal(stop_price) if stop_price is not None else None,
        time_in_force=time_in_force,
        client_order_id="test-001",
    )


# ---------------------------------------------------------------------------
# validate_order — reject cases
# ---------------------------------------------------------------------------


class TestValidateReject:
    def test_qty_below_min(self) -> None:
        req = _make_request(quantity="0.0001")
        with pytest.raises(InvalidOrderError, match="min_amount"):
            validate_order(req, _default_rules())

    def test_qty_above_max(self) -> None:
        req = _make_request(quantity="9999")
        with pytest.raises(InvalidOrderError, match="max_amount"):
            validate_order(req, _default_rules())

    def test_price_below_min(self) -> None:
        req = _make_request(price="0.001")
        with pytest.raises(InvalidOrderError, match="min_price"):
            validate_order(req, _default_rules())

    def test_price_above_max(self) -> None:
        req = _make_request(price="9999999")
        with pytest.raises(InvalidOrderError, match="max_price"):
            validate_order(req, _default_rules())

    def test_notional_below_min(self) -> None:
        req = _make_request(quantity="0.001", price="0.01")
        with pytest.raises(InvalidOrderError, match="min_notional"):
            validate_order(req, _default_rules())

    def test_unsupported_order_type(self) -> None:
        rules = _default_rules(supported_order_types=frozenset({OrderType.MARKET}))
        req = _make_request(order_type=OrderType.LIMIT)
        with pytest.raises(InvalidOrderError, match="order_type"):
            validate_order(req, rules)

    def test_unsupported_tif(self) -> None:
        rules = _default_rules(supported_tif=frozenset({TimeInForce.GTC}))
        req = _make_request(time_in_force=TimeInForce.FOK)
        with pytest.raises(InvalidOrderError, match="time_in_force"):
            validate_order(req, rules)

    def test_limit_without_price(self) -> None:
        req = _make_request(price=None, order_type=OrderType.LIMIT)
        with pytest.raises(InvalidOrderError, match="requires a price"):
            validate_order(req, _default_rules())

    def test_stop_limit_without_price(self) -> None:
        req = _make_request(price=None, order_type=OrderType.STOP_LIMIT)
        with pytest.raises(InvalidOrderError, match="requires a price"):
            validate_order(req, _default_rules())


# ---------------------------------------------------------------------------
# validate_order — happy path
# ---------------------------------------------------------------------------


class TestValidatePass:
    def test_limit_order(self) -> None:
        req = _make_request()
        validate_order(req, _default_rules())  # no raise

    def test_market_order_no_price(self) -> None:
        req = _make_request(price=None, order_type=OrderType.MARKET)
        validate_order(req, _default_rules())  # no raise


# ---------------------------------------------------------------------------
# quantize_order
# ---------------------------------------------------------------------------


class TestQuantizeOrder:
    def test_exact_step_no_change(self) -> None:
        req = _make_request(quantity="0.001", price="50000.00")
        result = quantize_order(req, _default_rules())
        assert result is req  # same object — no unnecessary copy

    def test_floor_quantity(self) -> None:
        req = _make_request(quantity="0.015")
        rules = _default_rules(amount_step=Decimal("0.001"))
        result = quantize_order(req, rules)
        assert result.quantity == Decimal("0.015")  # 0.015 / 0.001 = 15 exact

    def test_floor_quantity_rounds_down(self) -> None:
        req = _make_request(quantity="0.0149")
        rules = _default_rules(amount_step=Decimal("0.001"))
        result = quantize_order(req, rules)
        assert result.quantity == Decimal("0.014")

    def test_price_rounds_to_tick(self) -> None:
        req = _make_request(price="50000.555")
        rules = _default_rules(price_tick=Decimal("0.01"))
        result = quantize_order(req, rules)
        assert result.price == Decimal("50000.55")

    def test_price_floor_to_tick(self) -> None:
        req = _make_request(price="50000.009")
        rules = _default_rules(price_tick=Decimal("0.01"))
        result = quantize_order(req, rules)
        assert result.price == Decimal("50000.00")

    def test_decimal_places_precision(self) -> None:
        req = _make_request(quantity="1.23456", price="100.789")
        rules = _default_rules(
            amount_step=Decimal("0.0001"),
            price_tick=Decimal("0.01"),
            precision_mode=PrecisionMode.DECIMAL_PLACES,
        )
        result = quantize_order(req, rules)
        assert result.quantity == Decimal("1.2345")
        assert result.price == Decimal("100.78")

    def test_stop_price_quantized(self) -> None:
        req = _make_request(stop_price="49999.555")
        rules = _default_rules(price_tick=Decimal("0.01"))
        result = quantize_order(req, rules)
        assert result.stop_price == Decimal("49999.55")

    def test_none_price_unchanged(self) -> None:
        req = _make_request(price=None, order_type=OrderType.MARKET)
        result = quantize_order(req, _default_rules())
        assert result.price is None

    def test_new_frozen_instance(self) -> None:
        req = _make_request(quantity="0.0149")
        rules = _default_rules(amount_step=Decimal("0.001"))
        result = quantize_order(req, rules)
        assert result is not req
        assert result.client_order_id == req.client_order_id

    def test_significant_digits_not_implemented(self) -> None:
        req = _make_request(quantity="0.015")
        rules = _default_rules(
            amount_step=Decimal("0.001"),
            precision_mode=PrecisionMode.SIGNIFICANT_DIGITS,
        )
        with pytest.raises(NotImplementedError, match="SIGNIFICANT_DIGITS"):
            quantize_order(req, rules)
