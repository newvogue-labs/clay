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


# ---------------------------------------------------------------------------
# D-25/D-26: ack enrichment + type coercion (3.1–3.7)
# ---------------------------------------------------------------------------


def _make_request(
    *,
    symbol: str = "BTC/USDT",
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.LIMIT,
    quantity: Decimal = Decimal("0.001"),
    price: Decimal | None = Decimal("40000"),
    time_in_force: TimeInForce = TimeInForce.GTC,
    client_order_id: str = "cid-enrichment",
) -> OrderRequest:
    return OrderRequest(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        time_in_force=time_in_force,
        client_order_id=client_order_id,
    )


class TestD26AckEnrichment:
    """3.1 D-26 main: Bybit-like response without amount/status/side/type."""

    def test_bybit_create_order_response_fills_from_request(self) -> None:
        # Bybit unified createOrder returns id + clientOrderId but NOT amount/status/side/type
        resp = {"id": 2267705150334569728, "clientOrderId": "cid-enrichment"}
        req = _make_request()
        ack = _adapter()._ack_from_response("cid-enrichment", resp, requested=req)

        assert ack.quantity == Decimal("0.001")  # from requested, NOT Decimal("0")
        assert ack.price == Decimal("40000")  # from requested
        assert ack.side == OrderSide.BUY  # from requested
        assert ack.order_type == OrderType.LIMIT  # from requested
        assert ack.symbol == "BTC/USDT"  # from requested
        assert ack.state == OrderState.NEW  # status absent → "open" (not fabricated)
        assert ack.client_order_id == "cid-enrichment"

    def test_3_2_venue_priority_preserves_venue_value(self) -> None:
        """3.2 D-26: venue amount differs from requested → venue wins."""
        resp = {
            "id": "v-1",
            "symbol": "ETH/USDT",
            "amount": "0.02",
            "side": "sell",
            "type": "market",
        }
        req = _make_request(quantity=Decimal("0.001"), symbol="BTC/USDT")
        ack = _adapter()._ack_from_response("cid-1", resp, requested=req)

        assert ack.quantity == Decimal("0.02")  # venue value
        assert ack.symbol == "ETH/USDT"  # venue value
        assert ack.side == OrderSide.SELL  # venue value
        assert ack.order_type == OrderType.MARKET  # venue value

    def test_3_3_backward_compat_no_requested(self) -> None:
        """3.3 D-26: calling without requested=None → same as pre-slice."""
        resp = {"id": "v-1", "symbol": "BTC/USDT", "side": "sell", "type": "limit"}
        ack_no_req = _adapter()._ack_from_response("cid-1", resp)
        ack_with_none = _adapter()._ack_from_response("cid-1", resp, requested=None)
        assert ack_no_req.quantity == ack_with_none.quantity == Decimal("0")
        assert ack_no_req.side == ack_with_none.side == OrderSide.SELL
        assert ack_no_req.symbol == ack_with_none.symbol == "BTC/USDT"


class TestD27AckStatusAndAmountGuard:
    """D-27: Bybit DEMO status/amount guard + ack enrichment regression."""

    def test_2_1_status_none_yields_unknown_with_request_fallback(self) -> None:
        """Reproduces Bybit DEMO createOrder response (M405 live drill):
        status key present with None → UNKNOWN; quantity/price/side/type from request."""
        resp = {"id": "v-1", "status": None, "clientOrderId": "cid-enrichment"}
        req = _make_request(quantity=Decimal("0.001"), price=Decimal("40000"))
        ack = _adapter()._ack_from_response("cid-enrichment", resp, requested=req)

        assert ack.state == OrderState.UNKNOWN
        assert ack.quantity == Decimal("0.001")
        assert ack.price == Decimal("40000")
        assert ack.side == OrderSide.BUY
        assert ack.order_type == OrderType.LIMIT
        assert ack.symbol == "BTC/USDT"

    def test_2_2_status_empty_string_yields_unknown_with_request_fallback(self) -> None:
        """status='' → UNKNOWN; quantity/price/side/type from request."""
        resp = {"id": "v-1", "status": "", "clientOrderId": "cid-enrichment"}
        req = _make_request(quantity=Decimal("0.001"), price=Decimal("40000"))
        ack = _adapter()._ack_from_response("cid-enrichment", resp, requested=req)

        assert ack.state == OrderState.UNKNOWN
        assert ack.quantity == Decimal("0.001")
        assert ack.price == Decimal("40000")
        assert ack.side == OrderSide.BUY
        assert ack.order_type == OrderType.LIMIT

    # 2.3: contrast — status key ABSENT → NEW.
    # Covered by existing test_missing_status_defaults_to_open (TestD24AckStatusNoneGuard).

    def test_2_4_amount_empty_string_falls_back_to_request(self) -> None:
        """amount='' (venue silence) → quantity from requested, not Decimal('0')."""
        resp = {"id": "v-1", "amount": "", "status": "open"}
        req = _make_request(quantity=Decimal("0.001"))
        ack = _adapter()._ack_from_response("cid-1", resp, requested=req)

        assert ack.quantity == Decimal("0.001")

    def test_2_5_amount_zero_int_falls_back_to_request(self) -> None:
        """amount=0 (venue silence) → quantity from requested, not Decimal('0')."""
        resp = {"id": "v-1", "amount": 0, "status": "open"}
        req = _make_request(quantity=Decimal("0.001"))
        ack = _adapter()._ack_from_response("cid-1", resp, requested=req)

        assert ack.quantity == Decimal("0.001")

    # 2.6: venue-priority regression: amount="0.02" with requested.quantity=0.001 → 0.02.
    # Covered by existing test_3_2_venue_priority_preserves_venue_value.

    def test_2_7_backward_compat_no_requested_amount_zero(self) -> None:
        """Without requested and amount=0 → Decimal('0') (unchanged pre-D-26 behavior)."""
        resp = {"id": "v-1", "amount": 0}
        ack = _adapter()._ack_from_response("cid-1", resp)
        assert ack.quantity == Decimal("0")

    def test_2_7_backward_compat_no_requested_amount_empty(self) -> None:
        """Without requested and amount='' → Decimal('0') (unchanged pre-D-26 behavior)."""
        resp = {"id": "v-1", "amount": ""}
        ack = _adapter()._ack_from_response("cid-1", resp)
        assert ack.quantity == Decimal("0")


class TestD25TypeCoercion:
    def test_3_4_numeric_id_and_symbol_are_str(self) -> None:
        """3.4 D-25: numeric id and symbol → str in ack and snapshot."""
        resp = {"id": 2267705150334569728, "symbol": 12345, "status": "open"}
        ack = _adapter()._ack_from_response("cid-1", resp)
        assert isinstance(ack.venue_order_id, str)
        assert ack.venue_order_id == "2267705150334569728"
        assert isinstance(ack.symbol, str)
        assert ack.symbol == "12345"

        snap = _adapter()._snapshot_from_response(resp)
        assert isinstance(snap.venue_order_id, str)
        assert snap.venue_order_id == "2267705150334569728"
        assert isinstance(snap.symbol, str)
        assert snap.symbol == "12345"

    def test_3_5_fills_numeric_fields_are_str(self) -> None:
        """3.5 D-25: fills with numeric trade_id and commissionAsset → str."""
        resp = {
            "id": "1",
            "symbol": "BTC/USDT",
            "trades": [
                {
                    "id": 99999,
                    "side": "buy",
                    "amount": "1",
                    "price": "100",
                    "commission": "0.05",
                    "commissionAsset": 42,
                    "timestamp": 1700000000000,
                }
            ],
        }
        fills = _adapter()._fills_from_trades(resp)
        assert len(fills) == 1
        assert isinstance(fills[0].trade_id, str)
        assert fills[0].trade_id == "99999"
        assert isinstance(fills[0].commission_asset, str)
        assert fills[0].commission_asset == "42"

    def test_3_6_none_coerces_to_empty_string(self) -> None:
        """3.6 D-25/D-24 regression: None → '' on all string sites."""
        resp = {
            "id": None,
            "symbol": None,
            "clientOrderId": None,
            "trades": [
                {
                    "id": None,
                    "commissionAsset": None,
                }
            ],
        }
        ack = _adapter()._ack_from_response("cid-fallback", resp)
        assert ack.venue_order_id == ""
        assert ack.symbol == ""
        assert ack.client_order_id == "cid-fallback"  # fallback from param

        fills = _adapter()._fills_from_trades(resp)
        assert fills[0].trade_id == ""
        assert fills[0].commission_asset == ""

    def test_3_7_normal_path_unchanged(self) -> None:
        """3.7 Full valid response → identical to pre-slice behavior."""
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
        req = _make_request()
        ack = _adapter()._ack_from_response("cid-orig", resp, requested=req)
        # venue values take priority
        assert ack.venue_order_id == "venue-123"
        assert ack.client_order_id == "my-cid"
        assert ack.symbol == "BTC/USDT"
        assert ack.side == OrderSide.SELL
        assert ack.order_type == OrderType.MARKET
        assert ack.state == OrderState.FILLED
        assert ack.quantity == Decimal("0.5")
        assert ack.price == Decimal("51000")
        assert ack.transact_time == 1700000000000
        assert len(ack.fills) == 1
