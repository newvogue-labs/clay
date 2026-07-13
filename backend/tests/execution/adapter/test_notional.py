"""Tests for notional cap module (ported guards.py, S-LIVE-2, Decimal)."""

from decimal import Decimal

import pytest

from clay.execution.adapter.errors import OperationNotAllowedError
from clay.execution.adapter.notional import check_order_notional


class TestCheckOrderNotional:
    def test_off_by_default_allows_any_notional(self):
        check_order_notional(
            symbol="BTCUSDT",
            quantity=Decimal("100"),
            price=Decimal("100000"),
            max_notional=Decimal("0"),
        )

    def test_on_under_cap_allows(self):
        check_order_notional(
            symbol="BTCUSDT",
            quantity=Decimal("0.0001"),
            price=Decimal("100000"),
            max_notional=Decimal("50"),
        )

    def test_on_equal_cap_allows(self):
        check_order_notional(
            symbol="BTCUSDT",
            quantity=Decimal("0.0005"),
            price=Decimal("100000"),
            max_notional=Decimal("50"),
        )

    def test_on_over_cap_raises(self):
        with pytest.raises(
            OperationNotAllowedError, match="exceeds cap"
        ):
            check_order_notional(
                symbol="BTCUSDT",
                quantity=Decimal("0.01"),
                price=Decimal("100000"),
                max_notional=Decimal("50"),
            )

    def test_on_missing_price_fails_closed(self):
        with pytest.raises(
            OperationNotAllowedError, match="price is unknown"
        ):
            check_order_notional(
                symbol="BTCUSDT",
                quantity=Decimal("0.01"),
                price=None,
                max_notional=Decimal("50"),
            )

    def test_on_missing_price_with_zero_cap_does_not_fail(self):
        check_order_notional(
            symbol="BTCUSDT",
            quantity=Decimal("0.01"),
            price=None,
            max_notional=Decimal("0"),
        )
