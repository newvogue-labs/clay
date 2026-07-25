"""Tests for ccxt_base None-guard (D-20, D-24) and fail-closed routing (D-19).

All tests are hermetic — no network, no real ccxt client.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

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
    OrderState,
    OrderType,
    TimeInForce,
)
from clay.execution.adapter.errors import AmbiguousExecutionError, ConfigError
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


# ---------------------------------------------------------------------------
# D-24: read-mapping None sweep — D3.1
# ---------------------------------------------------------------------------


def _adapter() -> _StubAdapter:
    return _StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")  # type: ignore[arg-type]


class TestAckFromResponseNoneGuard:
    def test_timestamp_none_crashes_before_now_safely(self) -> None:
        """timestamp=None was a CRASH (int(None)). Now returns 0."""
        resp = {"id": "1", "symbol": "BTC/USDT", "status": "open", "timestamp": None}
        ack = _adapter()._ack_from_response("cid-1", resp)
        assert ack.transact_time == 0

    def test_id_none_not_poisoned(self) -> None:
        """id=None was POISON (str(None)='None'). Now empty string."""
        resp = {"id": None, "symbol": "BTC/USDT", "status": "open"}
        ack = _adapter()._ack_from_response("cid-1", resp)
        assert ack.venue_order_id == ""
        assert ack.venue_order_id != "None"

    def test_symbol_none_not_poisoned(self) -> None:
        """symbol=None was POISON. Now empty string."""
        resp = {"id": "1", "symbol": None, "status": "open"}
        ack = _adapter()._ack_from_response("cid-1", resp)
        assert ack.symbol == ""
        assert ack.symbol != "None"

    def test_status_none_yields_unknown(self) -> None:
        """status=None → UNKNOWN (not NEW, not crash)."""
        resp = {"id": "1", "symbol": "BTC/USDT", "status": None}
        ack = _adapter()._ack_from_response("cid-1", resp)
        assert ack.state == OrderState.UNKNOWN

    def test_status_empty_string_yields_unknown(self) -> None:
        """status='' → UNKNOWN."""
        resp = {"id": "1", "symbol": "BTC/USDT", "status": ""}
        ack = _adapter()._ack_from_response("cid-1", resp)
        assert ack.state == OrderState.UNKNOWN

    def test_missing_status_defaults_to_open(self) -> None:
        """status key absent → current behavior (open → NEW)."""
        resp = {"id": "1", "symbol": "BTC/USDT"}
        ack = _adapter()._ack_from_response("cid-1", resp)
        assert ack.state == OrderState.NEW


class TestSnapshotFromResponseNoneGuard:
    def test_timestamp_none_crashes_before_now_safely(self) -> None:
        resp = {"id": "1", "symbol": "BTC/USDT", "status": "open", "timestamp": None}
        snap = _adapter()._snapshot_from_response(resp)
        assert snap.transact_time == 0

    def test_id_none_not_poisoned(self) -> None:
        resp = {"id": None, "symbol": "BTC/USDT", "status": "open"}
        snap = _adapter()._snapshot_from_response(resp)
        assert snap.venue_order_id == ""
        assert snap.venue_order_id != "None"

    def test_symbol_none_not_poisoned(self) -> None:
        resp = {"id": "1", "symbol": None, "status": "open"}
        snap = _adapter()._snapshot_from_response(resp)
        assert snap.symbol == ""
        assert snap.symbol != "None"

    def test_status_none_yields_unknown(self) -> None:
        resp = {"id": "1", "symbol": "BTC/USDT", "status": None}
        snap = _adapter()._snapshot_from_response(resp)
        assert snap.state == OrderState.UNKNOWN


class TestFillsFromTradesNoneGuard:
    def test_trades_none_returns_empty(self) -> None:
        resp = {"id": "1", "symbol": "BTC/USDT", "trades": None}
        fills = _adapter()._fills_from_trades(resp)
        assert fills == []

    def test_fill_fields_none_no_poison(self) -> None:
        resp = {
            "id": "1",
            "symbol": "BTC/USDT",
            "trades": [
                {
                    "id": None,
                    "side": None,
                    "amount": None,
                    "price": None,
                    "commission": None,
                    "commissionAsset": None,
                    "timestamp": None,
                }
            ],
        }
        fills = _adapter()._fills_from_trades(resp)
        assert len(fills) == 1
        f = fills[0]
        assert f.trade_id == ""
        assert f.trade_id != "None"
        # symbol comes from response-level, not fill-level
        assert f.symbol == "BTC/USDT"
        assert f.commission_asset == ""
        assert f.transact_time == 0
        assert f.side == OrderSide.BUY


class TestFillFromMyTradeNoneGuard:
    def test_trade_id_none(self) -> None:
        trade = {"id": None, "order": None, "symbol": None, "side": None}
        fill = _fill_from_my_trade(trade)
        assert fill.trade_id == ""
        assert fill.venue_order_id == ""
        assert fill.symbol == ""
        assert fill.side == OrderSide.BUY

    def test_timestamp_none_crashes_before_now_safely(self) -> None:
        trade = {"timestamp": None}
        fill = _fill_from_my_trade(trade)
        assert fill.transact_time == 0


class TestGetBalancesNoneGuard:
    @pytest.mark.anyio
    async def test_total_none_does_not_crash(self) -> None:
        """total=None was CRASH (None.items()). Now empty dict."""
        adapter = _StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")  # type: ignore[arg-type]
        resp = {"total": None, "free": None, "used": None}
        adapter._client.fetch_balance = AsyncMock(return_value=resp)  # type: ignore[assignment]
        balances = await adapter.get_balances()
        assert balances == []


# ---------------------------------------------------------------------------
# D-24: D3.2 — regression: normal path unchanged
# ---------------------------------------------------------------------------


class TestAckFromResponseNormalPath:
    def test_full_normal_response_preserves_values(self) -> None:
        resp = {
            "id": "venue-123",
            "clientOrderId": "my-cid",
            "symbol": "BTC/USDT",
            "side": "sell",
            "type": "market",
            "status": "closed",
            "amount": "0.5",
            "filled": "0.5",
            "price": "51000",
            "timestamp": 1700000000000,
            "trades": [
                {
                    "id": "t1",
                    "side": "sell",
                    "amount": "0.5",
                    "price": "51000",
                    "commission": "0.05",
                    "commissionAsset": "USDT",
                    "timestamp": 1700000000000,
                }
            ],
        }
        ack = _adapter()._ack_from_response("cid-orig", resp)
        assert ack.venue_order_id == "venue-123"
        assert ack.client_order_id == "my-cid"
        assert ack.symbol == "BTC/USDT"
        assert ack.side == OrderSide.SELL
        assert ack.order_type == OrderType.MARKET
        assert ack.state == OrderState.FILLED
        assert ack.transact_time == 1700000000000
        assert len(ack.fills) == 1
        assert ack.fills[0].trade_id == "t1"


# ---------------------------------------------------------------------------
# D-24: D3.3 — place_order parse failure → AmbiguousExecutionError
# ---------------------------------------------------------------------------


class TestPlaceOrderParseFailureAmbiguous:
    @pytest.mark.anyio
    async def test_parse_failure_after_create_raises_ambiguous(self) -> None:
        """Successful create_order + _ack_from_response raises → AmbiguousExecutionError."""
        adapter = _StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")  # type: ignore[arg-type]

        # Make _ack_from_response raise
        def _broken_ack(client_order_id: str, response: dict[str, Any]) -> Any:
            raise TypeError("simulated parse failure")

        adapter._ack_from_response = _broken_ack  # type: ignore[assignment]
        # Async mock for create_order
        adapter._client.create_order = AsyncMock(  # type: ignore[assignment]
            return_value={"id": "1", "symbol": "BTC/USDT"}
        )

        req = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            time_in_force=TimeInForce.GTC,
            client_order_id="test-cid-ambiguous",
        )

        with pytest.raises(AmbiguousExecutionError, match="test-cid-ambiguous"):
            await adapter.place_order(req)
