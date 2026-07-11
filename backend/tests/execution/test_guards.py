import pytest

from clay.execution.exceptions import OrderRejectedError
from clay.execution.guards import check_order_notional


def test_guard_off_by_default_allows_any_notional() -> None:
    check_order_notional(
        symbol="BTCUSDT", quantity=100.0, price=100000.0, max_notional_usdt=0.0
    )


def test_guard_on_under_cap_allows() -> None:  # 10 <= 50
    check_order_notional(
        symbol="BTCUSDT", quantity=0.0001, price=100000.0, max_notional_usdt=50.0
    )


def test_guard_on_equal_cap_allows() -> None:  # 50 == 50, not > → allow
    check_order_notional(
        symbol="BTCUSDT", quantity=0.0005, price=100000.0, max_notional_usdt=50.0
    )


def test_guard_on_over_cap_raises() -> None:  # 1000 > 50
    with pytest.raises(OrderRejectedError):
        check_order_notional(
            symbol="BTCUSDT", quantity=0.01, price=100000.0, max_notional_usdt=50.0
        )


def test_guard_on_missing_price_fails_closed() -> None:
    with pytest.raises(OrderRejectedError):
        check_order_notional(
            symbol="BTCUSDT", quantity=0.01, price=None, max_notional_usdt=50.0
        )
