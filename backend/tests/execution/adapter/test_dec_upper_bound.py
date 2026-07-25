"""D-23: _dec_upper_bound helper — upper-bound sentinel parsing."""

from decimal import Decimal
from unittest.mock import patch

from clay.execution.adapter.ccxt_base import _dec_upper_bound


class TestDecUpperBound:
    def test_none_returns_none(self) -> None:
        assert (
            _dec_upper_bound(None, field="max_price", symbol="BTC/USDT", venue="bybit")
            is None
        )

    def test_empty_string_returns_none(self) -> None:
        assert (
            _dec_upper_bound("", field="max_price", symbol="BTC/USDT", venue="bybit")
            is None
        )

    def test_whitespace_returns_none(self) -> None:
        assert (
            _dec_upper_bound("  ", field="max_price", symbol="BTC/USDT", venue="bybit")
            is None
        )

    def test_positive_value_returns_decimal(self) -> None:
        result = _dec_upper_bound(
            "1999999.80", field="max_price", symbol="BTC/USDT", venue="bybit"
        )
        assert result == Decimal("1999999.80")

    def test_positive_int_returns_decimal(self) -> None:
        result = _dec_upper_bound(
            1500, field="max_amount", symbol="BTC/USDT", venue="bybit"
        )
        assert result == Decimal("1500")

    def test_zero_returns_none_with_warning(self) -> None:
        with patch("clay.execution.adapter.ccxt_base.logger") as mock_log:
            result = _dec_upper_bound(
                0, field="max_price", symbol="BTC/USDT", venue="bybit"
            )
        assert result is None
        mock_log.warning.assert_called_once()
        assert "non-positive upper bound" in mock_log.warning.call_args[0][0]

    def test_negative_returns_none_with_warning(self) -> None:
        with patch("clay.execution.adapter.ccxt_base.logger") as mock_log:
            result = _dec_upper_bound(
                "-100", field="max_amount", symbol="ETH/USDT", venue="binance"
            )
        assert result is None
        mock_log.warning.assert_called_once()

    def test_no_warning_on_positive_value(self) -> None:
        with patch("clay.execution.adapter.ccxt_base.logger") as mock_log:
            result = _dec_upper_bound(
                "500", field="max_price", symbol="BTC/USDT", venue="binance"
            )
        assert result == Decimal("500")
        mock_log.warning.assert_not_called()
