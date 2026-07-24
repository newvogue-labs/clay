"""Tests for ccxt_base None-guard (D-20) and fail-closed routing (D-19).

All tests are hermetic — no network, no real ccxt client.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from clay.execution.adapter.ccxt_base import (
    CcxtExchangeAdapter,
    _apply_sandbox_routing,
    _fill_from_my_trade,
)
from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import (
    Environment,
    OrderSide,
    OrderType,
    TimeInForce,
)
from clay.execution.adapter.errors import ConfigError
from clay.execution.adapter.rules import MarketRules


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing CcxtExchangeAdapter methods
# ---------------------------------------------------------------------------


class _StubAdapter(CcxtExchangeAdapter):
    """Minimal concrete adapter — delegates all methods to raise NotImplementedError."""

    supported_order_types = frozenset({OrderType.LIMIT})
    supported_tif = frozenset({TimeInForce.GTC})

    def _build_client(self, api_key: str, api_secret: str) -> Any:
        return MagicMock()

    def _is_duplicate_cid(self, exc: Exception) -> bool:
        return False

    def _build_order_params(self, req: OrderRequest) -> dict[str, Any]:
        return {}

    async def get_market_rules(self, symbol: str) -> MarketRules:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# A-tests: None-guard on enum parsing (D-20)
# ---------------------------------------------------------------------------


class TestNoneGuardAckFromResponse:
    def test_side_none_defaults_to_buy(self) -> None:
        adapter = _StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")  # type: ignore[arg-type]
        resp = {"side": None, "type": None, "status": "open", "id": "1"}
        ack = adapter._ack_from_response("cid-1", resp)
        assert ack.side == OrderSide.BUY
        assert ack.order_type == OrderType.LIMIT

    def test_side_sell_preserved(self) -> None:
        adapter = _StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")  # type: ignore[arg-type]
        resp = {"side": "sell", "type": "market", "status": "closed", "id": "1"}
        ack = adapter._ack_from_response("cid-1", resp)
        assert ack.side == OrderSide.SELL
        assert ack.order_type == OrderType.MARKET


class TestNoneGuardSnapshotFromResponse:
    def test_side_none_defaults_to_buy(self) -> None:
        adapter = _StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")  # type: ignore[arg-type]
        resp = {"side": None, "type": None, "status": "open", "id": "1"}
        snap = adapter._snapshot_from_response(resp)
        assert snap.side == OrderSide.BUY
        assert snap.order_type == OrderType.LIMIT

    def test_side_sell_preserved(self) -> None:
        adapter = _StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")  # type: ignore[arg-type]
        resp = {"side": "sell", "type": "market", "status": "closed", "id": "1"}
        snap = adapter._snapshot_from_response(resp)
        assert snap.side == OrderSide.SELL
        assert snap.order_type == OrderType.MARKET


class TestNoneGuardFillsFromTrades:
    def test_fill_side_none_defaults_to_buy(self) -> None:
        adapter = _StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")  # type: ignore[arg-type]
        resp = {
            "id": "1",
            "symbol": "BTC/USDT",
            "trades": [{"side": None, "amount": "1", "price": "100"}],
        }
        fills = adapter._fills_from_trades(resp)
        assert len(fills) == 1
        assert fills[0].side == OrderSide.BUY

    def test_fill_side_sell_preserved(self) -> None:
        adapter = _StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")  # type: ignore[arg-type]
        resp = {
            "id": "1",
            "symbol": "BTC/USDT",
            "trades": [{"side": "sell", "amount": "1", "price": "100"}],
        }
        fills = adapter._fills_from_trades(resp)
        assert fills[0].side == OrderSide.SELL


class TestNoneGuardFillFromMyTrade:
    def test_trade_side_none_defaults_to_buy(self) -> None:
        trade = {"side": None, "amount": "1", "price": "100"}
        fill = _fill_from_my_trade(trade)
        assert fill.side == OrderSide.BUY

    def test_trade_side_sell_preserved(self) -> None:
        trade = {"side": "sell", "amount": "1", "price": "100"}
        fill = _fill_from_my_trade(trade)
        assert fill.side == OrderSide.SELL


# ---------------------------------------------------------------------------
# B-tests: fail-closed env routing (D-19)
# ---------------------------------------------------------------------------


class TestApplySandboxRouting:
    def test_testnet_sets_sandbox(self) -> None:
        client = MagicMock()
        _apply_sandbox_routing(client, Environment.TESTNET)
        client.set_sandbox_mode.assert_called_once_with(True)

    def test_production_noop(self) -> None:
        client = MagicMock()
        _apply_sandbox_routing(client, Environment.PRODUCTION)
        client.set_sandbox_mode.assert_not_called()

    def test_demo_raises_config_error(self) -> None:
        client = MagicMock()
        with pytest.raises(ConfigError, match="not supported"):
            _apply_sandbox_routing(client, Environment.DEMO)

    def test_paper_raises_config_error(self) -> None:
        client = MagicMock()
        with pytest.raises(ConfigError, match="not supported"):
            _apply_sandbox_routing(client, Environment.PAPER)


class TestBinanceRouting:
    def test_testnet_sets_sandbox(self) -> None:
        from clay.execution.adapter.binance import BinanceExecutionAdapter

        client = MagicMock()
        BinanceExecutionAdapter(Environment.TESTNET, client=client)  # type: ignore[arg-type]
        client.set_sandbox_mode.assert_called_once_with(True)

    def test_production_noop(self) -> None:
        from clay.execution.adapter.binance import BinanceExecutionAdapter

        client = MagicMock()
        BinanceExecutionAdapter(Environment.PRODUCTION, client=client)  # type: ignore[arg-type]
        client.set_sandbox_mode.assert_not_called()

    def test_demo_raises_config_error(self) -> None:
        from clay.execution.adapter.binance import BinanceExecutionAdapter

        client = MagicMock()
        with pytest.raises(ConfigError, match="not supported"):
            BinanceExecutionAdapter(Environment.DEMO, client=client)  # type: ignore[arg-type]

    def test_paper_raises_config_error(self) -> None:
        from clay.execution.adapter.binance import BinanceExecutionAdapter

        client = MagicMock()
        with pytest.raises(ConfigError, match="not supported"):
            BinanceExecutionAdapter(Environment.PAPER, client=client)  # type: ignore[arg-type]


class TestBybitRoutingStillWorks:
    """Regression: existing Bybit DEMO→enable_demo_trading must remain green."""

    def test_bybit_demo_enables_demo_trading(self) -> None:
        from tests.execution.adapter.test_bybit import FakeBybitClient

        from clay.execution.adapter.bybit import BybitExecutionAdapter

        client = FakeBybitClient()
        BybitExecutionAdapter(Environment.DEMO, client=client)  # type: ignore[arg-type]
        assert client._demo_trading is True
        assert client._sandbox is False

    def test_bybit_testnet_sets_sandbox(self) -> None:
        from tests.execution.adapter.test_bybit import FakeBybitClient

        from clay.execution.adapter.bybit import BybitExecutionAdapter

        client = FakeBybitClient()
        BybitExecutionAdapter(Environment.TESTNET, client=client)  # type: ignore[arg-type]
        assert client._sandbox is True
        assert client._demo_trading is False

    def test_bybit_production_no_side_effects(self) -> None:
        from tests.execution.adapter.test_bybit import FakeBybitClient

        from clay.execution.adapter.bybit import BybitExecutionAdapter

        client = FakeBybitClient()
        BybitExecutionAdapter(Environment.PRODUCTION, client=client)  # type: ignore[arg-type]
        assert client._sandbox is False
        assert client._demo_trading is False
        assert client._calls == []

    def test_bybit_paper_raises_config_error(self) -> None:
        from tests.execution.adapter.test_bybit import FakeBybitClient

        from clay.execution.adapter.bybit import BybitExecutionAdapter

        client = FakeBybitClient()
        with pytest.raises(ConfigError, match="not supported by Bybit adapter"):
            BybitExecutionAdapter(Environment.PAPER, client=client)  # type: ignore[arg-type]
