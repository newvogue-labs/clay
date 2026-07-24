"""Tests for BinanceExecutionAdapter — offline (ccxt mocked, no network)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import ccxt.async_support as ccxt
import pytest

from clay.execution.adapter.binance import (
    BinanceExecutionAdapter,
    _is_duplicate_cid,
)
from clay.execution.adapter.ccxt_base import _map_state
from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import (
    CancelResult,
    Environment,
    OrderSide,
    OrderState,
    OrderType,
    PrecisionMode,
    TimeInForce,
)
from clay.execution.adapter.errors import (
    AmbiguousExecutionError,
    ConfigError,
    InsufficientFundsError,
    InvalidOrderError,
    OrderNotFoundError,
    OrderRejectedError,
    TransientAdapterError,
)
from clay.execution.adapter.port import ExchangeAdapter
from clay.execution.adapter.rules import MarketRules
from clay.execution.resilience import RetryPolicy, ResilientExecutionAdapter


# ---------------------------------------------------------------------------
# FakeBinanceClient — in-memory stand-in for ccxt.binance
# ---------------------------------------------------------------------------


class FakeBinanceClient:
    """Mimics the ccxt.binance async interface used by BinanceExecutionAdapter."""

    def __init__(self) -> None:
        self._markets: dict[str, Any] = {}
        self._orders: dict[str, dict[str, Any]] = {}
        self._balances: dict[str, Any] = {"total": {}, "free": {}, "used": {}}
        self._open_orders: list[dict[str, Any]] = []
        self._all_orders: list[dict[str, Any]] = []
        self._sandbox = False
        self._closed = False

    def set_sandbox_mode(self, enabled: bool) -> None:
        self._sandbox = enabled

    async def load_markets(self) -> dict[str, Any]:
        return self._markets

    async def create_order(
        self,
        *,
        symbol: str,
        type: str,
        side: str,
        amount: str,
        price: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params = params or {}
        order_id = params.get("newClientOrderId", "order-1")
        response = {
            "id": order_id,
            "clientOrderId": params.get("newClientOrderId", order_id),
            "symbol": symbol,
            "side": side,
            "type": type,
            "amount": amount,
            "price": price or "0",
            "filled": amount,
            "status": "closed",
            "timestamp": 1700000000000,
            "trades": [],
        }
        self._orders[order_id] = response
        self._all_orders.append(response)
        return response

    async def cancel_order(
        self,
        *,
        id: str,
        symbol: str,  # noqa: A002
    ) -> dict[str, Any]:
        if id not in self._orders:
            raise ccxt.OrderNotFound(f"order {id} not found")
        return {"id": id, "status": "canceled"}

    async def fetch_order(
        self,
        *,
        id: str,
        symbol: str,  # noqa: A002
    ) -> dict[str, Any]:
        if id not in self._orders:
            raise ccxt.OrderNotFound(f"order {id} not found")
        return self._orders[id]

    async def fetch_open_orders(
        self, symbol: str | None = None
    ) -> list[dict[str, Any]]:
        return list(self._open_orders)

    async def fetch_orders(
        self, symbol: str | None = None, since: int | None = None
    ) -> list[dict[str, Any]]:
        return list(self._all_orders)

    async def fetch_balance(self) -> dict[str, Any]:
        return dict(self._balances)

    async def close(self) -> None:
        self._closed = True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_rules(**overrides: object) -> MarketRules:
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
    price: str | None = "50000",
    quantity: str = "0.01",
    order_type: OrderType = OrderType.LIMIT,
    client_order_id: str = "test-001",
) -> OrderRequest:
    return OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=order_type,
        quantity=Decimal(quantity),
        price=Decimal(price) if price is not None else None,
        time_in_force=TimeInForce.GTC,
        client_order_id=client_order_id,
    )


def _make_binance_market() -> dict[str, Any]:
    """Return a fake Binance market dict (as returned by load_markets)."""
    return {
        "id": "BTCUSDT",
        "symbol": "BTC/USDT",
        "base": "BTC",
        "quote": "USDT",
        "precision": {"amount": "0.001", "price": "0.01"},
        "limits": {
            "amount": {"min": "0.001", "max": "1000"},
            "price": {"min": "0.01", "max": "1000000"},
            "cost": {"min": "10"},
        },
        "info": {
            "filters": [
                {
                    "filterType": "LOT_SIZE",
                    "minQty": "0.001",
                    "maxQty": "1000",
                    "stepSize": "0.001",
                },
                {
                    "filterType": "PRICE_FILTER",
                    "minPrice": "0.01",
                    "maxPrice": "1000000",
                    "tickSize": "0.01",
                },
                {
                    "filterType": "NOTIONAL",
                    "minNotional": "10",
                },
            ]
        },
    }


def _adapter(client: FakeBinanceClient | None = None) -> BinanceExecutionAdapter:
    if client is None:
        client = FakeBinanceClient()
    return BinanceExecutionAdapter(Environment.PRODUCTION, client=client)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _map_state
# ---------------------------------------------------------------------------


class TestMapState:
    def test_open_no_fills(self) -> None:
        assert _map_state("open", Decimal("0")) == OrderState.NEW

    def test_open_with_fills(self) -> None:
        assert _map_state("open", Decimal("0.5")) == OrderState.PARTIALLY_FILLED

    def test_closed(self) -> None:
        assert _map_state("closed", Decimal("1")) == OrderState.FILLED

    def test_canceled(self) -> None:
        assert _map_state("canceled", Decimal("0")) == OrderState.CANCELED

    def test_rejected(self) -> None:
        assert _map_state("rejected", Decimal("0")) == OrderState.REJECTED

    def test_expired(self) -> None:
        assert _map_state("expired", Decimal("0")) == OrderState.EXPIRED

    def test_unknown_defaults_to_unknown(self) -> None:
        assert _map_state("weird_status", Decimal("0")) == OrderState.UNKNOWN


# ---------------------------------------------------------------------------
# Protocol check
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_satisfies_exchange_adapter(self) -> None:
        assert isinstance(_adapter(), ExchangeAdapter)

    def test_environment_attribute(self) -> None:
        assert _adapter().environment == Environment.PRODUCTION


# ---------------------------------------------------------------------------
# get_market_rules
# ---------------------------------------------------------------------------


class TestGetMarketRules:
    @pytest.mark.anyio
    async def test_parses_filters(self) -> None:
        client = FakeBinanceClient()
        client._markets = {"BTCUSDT": _make_binance_market()}
        adapter = _adapter(client)

        rules = await adapter.get_market_rules("BTCUSDT")

        assert rules.min_amount == Decimal("0.001")
        assert rules.max_amount == Decimal("1000")
        assert rules.min_price == Decimal("0.01")
        assert rules.max_price == Decimal("1000000")
        assert rules.min_notional == Decimal("10")
        assert rules.amount_step == Decimal("0.001")
        assert rules.price_tick == Decimal("0.01")
        assert rules.precision_mode == PrecisionMode.TICK_SIZE

    @pytest.mark.anyio
    async def test_unknown_symbol_raises(self) -> None:
        client = FakeBinanceClient()
        client._markets = {}
        adapter = _adapter(client)

        with pytest.raises(InvalidOrderError, match="unknown symbol"):
            await adapter.get_market_rules("NONEXIST")

    @pytest.mark.anyio
    async def test_network_error_is_transient(self) -> None:
        client = FakeBinanceClient()
        client.load_markets = AsyncMock(side_effect=ccxt.NetworkError("timeout"))  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(TransientAdapterError):
            await adapter.get_market_rules("BTCUSDT")

    @pytest.mark.anyio
    async def test_auth_error_is_config(self) -> None:
        client = FakeBinanceClient()
        client.load_markets = AsyncMock(side_effect=ccxt.AuthenticationError("bad"))  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(ConfigError):
            await adapter.get_market_rules("BTCUSDT")


# ---------------------------------------------------------------------------
# place_order
# ---------------------------------------------------------------------------


class TestPlaceOrder:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        client = FakeBinanceClient()
        adapter = _adapter(client)
        req = _make_request()

        ack = await adapter.place_order(req)

        assert ack.client_order_id == "test-001"
        assert ack.venue_order_id == "test-001"
        assert ack.symbol == "BTCUSDT"
        assert ack.side == OrderSide.BUY
        assert ack.order_type == OrderType.LIMIT
        assert ack.state == OrderState.FILLED
        assert isinstance(ack.quantity, Decimal)
        assert isinstance(ack.price, Decimal)
        assert ack.transact_time == 1700000000000
        assert isinstance(ack.fills, tuple)

    @pytest.mark.anyio
    async def test_insufficient_funds_error(self) -> None:
        client = FakeBinanceClient()
        client.create_order = AsyncMock(side_effect=ccxt.InsufficientFunds("no funds"))  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(InsufficientFundsError):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_invalid_order_error(self) -> None:
        client = FakeBinanceClient()
        client.create_order = AsyncMock(side_effect=ccxt.InvalidOrder("bad qty"))  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(InvalidOrderError):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_network_error_is_ambiguous(self) -> None:
        client = FakeBinanceClient()
        client.create_order = AsyncMock(side_effect=ccxt.NetworkError("timeout"))  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(AmbiguousExecutionError):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_exchange_error_is_rejected(self) -> None:
        client = FakeBinanceClient()
        client.create_order = AsyncMock(side_effect=ccxt.ExchangeError("generic"))  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(OrderRejectedError):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_auth_error_is_config(self) -> None:
        client = FakeBinanceClient()
        client.create_order = AsyncMock(side_effect=ccxt.AuthenticationError("bad key"))  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(ConfigError):
            await adapter.place_order(_make_request())


# ---------------------------------------------------------------------------
# _is_duplicate_cid (unit)
# ---------------------------------------------------------------------------


class TestIsDuplicateCid:
    def test_spot_error_code(self) -> None:
        assert _is_duplicate_cid(
            ccxt.ExchangeError("binance -4116 DUPLICATED_CLIENT_ORDER_ID")
        )

    def test_futures_error_code(self) -> None:
        assert _is_duplicate_cid(
            ccxt.InvalidOrder("binance -4116 DUPLICATED_CLIENT_ORDER_ID")
        )

    def test_code_only(self) -> None:
        assert _is_duplicate_cid(ccxt.ExchangeError("binance -4116"))

    def test_message_only(self) -> None:
        assert _is_duplicate_cid(ccxt.ExchangeError("DUPLICATED_CLIENT_ORDER_ID"))

    def test_unrelated_exchange_error(self) -> None:
        assert not _is_duplicate_cid(ccxt.ExchangeError("generic error"))

    def test_unrelated_invalid_order(self) -> None:
        assert not _is_duplicate_cid(ccxt.InvalidOrder("LOT_SIZE filter failure"))

    def test_empty_message(self) -> None:
        assert not _is_duplicate_cid(ccxt.ExchangeError(""))


# ---------------------------------------------------------------------------
# place_order: duplicate clientOrderId → AmbiguousExecutionError
# ---------------------------------------------------------------------------


_DUPLICATE_CID_SPOT_MSG = (
    "binance POST https://api.binance.com/api/v3/order 400 "
    '{"code":-4116,"msg":"DUPLICATED_CLIENT_ORDER_ID"}'
)
_DUPLICATE_CID_FUTURES_MSG = (
    "binance POST https://fapi.binance.com/fapi/v1/order 400 "
    '{"code":-4116,"msg":"DUPLICATED_CLIENT_ORDER_ID"}'
)


class TestPlaceOrderDuplicateCid:
    """Duplicate clientOrderId must raise AmbiguousExecutionError, not terminal."""

    @pytest.mark.anyio
    async def test_spot_exchange_error_is_ambiguous(self) -> None:
        """Binance Spot maps -4116 → ExchangeError (not InvalidOrder)."""
        client = FakeBinanceClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.ExchangeError(_DUPLICATE_CID_SPOT_MSG)
        )  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(AmbiguousExecutionError, match="-4116"):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_futures_invalid_order_is_ambiguous(self) -> None:
        """USDT-M Futures maps -4116 → InvalidOrder — still ambiguous."""
        client = FakeBinanceClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.InvalidOrder(_DUPLICATE_CID_FUTURES_MSG)
        )  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(AmbiguousExecutionError, match="-4116"):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_cid_preserved_in_message(self) -> None:
        """AmbiguousExecutionError includes the client_order_id."""
        client = FakeBinanceClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.ExchangeError(_DUPLICATE_CID_SPOT_MSG)
        )  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(AmbiguousExecutionError, match="cid='test-001'"):
            await adapter.place_order(_make_request(client_order_id="test-001"))

    @pytest.mark.anyio
    async def test_invalid_order_without_dup_cid_stays_terminal(self) -> None:
        """InvalidOrder WITHOUT -4116 must still raise InvalidOrderError."""
        client = FakeBinanceClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.InvalidOrder("LOT_SIZE filter failure")
        )  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(InvalidOrderError):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_exchange_error_without_dup_cid_stays_rejected(self) -> None:
        """ExchangeError WITHOUT -4116 must still raise OrderRejectedError."""
        client = FakeBinanceClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.ExchangeError("some other error")
        )  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(OrderRejectedError):
            await adapter.place_order(_make_request())


# ---------------------------------------------------------------------------
# D4-regression: message contains actual venue error text
# ---------------------------------------------------------------------------


_DUPLICATE_CID_TEXT_MSG = (
    "binance POST https://api.binance.com/api/v3/order 400 "
    '{"code":-4116,"msg":"DUPLICATED_CLIENT_ORDER_ID"}'
)


class TestDuplicateCidMessageRegression:
    """Verify AmbiguousExecutionError message contains venue error text."""

    @pytest.mark.anyio
    async def test_duplicated_client_order_id_in_message(self) -> None:
        """DUPLICATED_CLIENT_ORDER_ID → message contains the venue error string."""
        client = FakeBinanceClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.ExchangeError(_DUPLICATE_CID_TEXT_MSG)
        )  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(
            AmbiguousExecutionError, match="DUPLICATED_CLIENT_ORDER_ID"
        ) as exc_info:
            await adapter.place_order(_make_request())
        msg = str(exc_info.value)
        assert "cid=" in msg

    @pytest.mark.anyio
    async def test_4116_still_ambiguous(self) -> None:
        """-4116 path still raises AmbiguousExecutionError (regression guard)."""
        client = FakeBinanceClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.InvalidOrder(_DUPLICATE_CID_FUTURES_MSG)
        )  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(AmbiguousExecutionError, match="-4116"):
            await adapter.place_order(_make_request())


class TestCancelOrder:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        client = FakeBinanceClient()
        client._orders["v-1"] = {"id": "v-1"}
        adapter = _adapter(client)

        result = await adapter.cancel_order("BTCUSDT", "v-1")
        assert result == CancelResult.CANCELED

    @pytest.mark.anyio
    async def test_order_not_found_returns_not_found(self) -> None:
        client = FakeBinanceClient()
        adapter = _adapter(client)

        result = await adapter.cancel_order("BTCUSDT", "nonexistent")
        assert result == CancelResult.NOT_FOUND

    @pytest.mark.anyio
    async def test_network_error_is_transient(self) -> None:
        client = FakeBinanceClient()
        client.cancel_order = AsyncMock(side_effect=ccxt.NetworkError("timeout"))  # type: ignore[assignment]
        adapter = _adapter(client)
        client._orders["v-1"] = {"id": "v-1"}

        with pytest.raises(TransientAdapterError):
            await adapter.cancel_order("BTCUSDT", "v-1")


# ---------------------------------------------------------------------------
# get_order
# ---------------------------------------------------------------------------


class TestGetOrder:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        client = FakeBinanceClient()
        client._orders["v-1"] = {
            "id": "v-1",
            "clientOrderId": "c-1",
            "symbol": "BTCUSDT",
            "side": "buy",
            "type": "limit",
            "amount": "0.01",
            "filled": "0",
            "price": "50000",
            "status": "open",
            "timestamp": 1700000000000,
            "trades": [],
        }
        adapter = _adapter(client)

        snap = await adapter.get_order("BTCUSDT", "v-1")

        assert snap.venue_order_id == "v-1"
        assert snap.client_order_id == "c-1"
        assert snap.state == OrderState.NEW
        assert isinstance(snap.quantity, Decimal)
        assert isinstance(snap.executed_qty, Decimal)

    @pytest.mark.anyio
    async def test_not_found_raises_order_not_found(self) -> None:
        client = FakeBinanceClient()
        adapter = _adapter(client)

        with pytest.raises(OrderNotFoundError) as exc_info:
            await adapter.get_order("BTCUSDT", "nonexistent")

        assert exc_info.value.venue_order_id == "nonexistent"
        assert exc_info.value.symbol == "BTCUSDT"

    @pytest.mark.anyio
    async def test_network_error_is_transient(self) -> None:
        client = FakeBinanceClient()
        client.fetch_order = AsyncMock(side_effect=ccxt.NetworkError("timeout"))  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(TransientAdapterError):
            await adapter.get_order("BTCUSDT", "v-1")


# ---------------------------------------------------------------------------
# get_open_orders
# ---------------------------------------------------------------------------


class TestGetOpenOrders:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        client = FakeBinanceClient()
        client._open_orders = [
            {
                "id": "v-1",
                "clientOrderId": "c-1",
                "symbol": "BTCUSDT",
                "side": "buy",
                "type": "limit",
                "amount": "0.01",
                "filled": "0",
                "price": "50000",
                "status": "open",
                "timestamp": 1700000000000,
                "trades": [],
            }
        ]
        adapter = _adapter(client)

        orders = await adapter.get_open_orders("BTCUSDT")

        assert len(orders) == 1
        assert orders[0].venue_order_id == "v-1"
        assert isinstance(orders[0].quantity, Decimal)

    @pytest.mark.anyio
    async def test_empty(self) -> None:
        client = FakeBinanceClient()
        adapter = _adapter(client)

        orders = await adapter.get_open_orders()
        assert orders == []


# ---------------------------------------------------------------------------
# reconcile_orders
# ---------------------------------------------------------------------------


class TestReconcileOrders:
    @pytest.mark.anyio
    async def test_calls_fetch_orders(self) -> None:
        client = FakeBinanceClient()
        client._all_orders = [
            {
                "id": "v-1",
                "clientOrderId": "c-1",
                "symbol": "BTCUSDT",
                "side": "buy",
                "type": "limit",
                "amount": "0.01",
                "filled": "0.01",
                "price": "50000",
                "status": "closed",
                "timestamp": 1700000000000,
                "trades": [],
            }
        ]
        adapter = _adapter(client)

        orders = await adapter.reconcile_orders("BTCUSDT", datetime(2024, 1, 1))

        assert len(orders) == 1
        assert orders[0].state == OrderState.FILLED

    @pytest.mark.anyio
    async def test_network_error_is_transient(self) -> None:
        client = FakeBinanceClient()
        client.fetch_orders = AsyncMock(side_effect=ccxt.NetworkError("timeout"))  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(TransientAdapterError):
            await adapter.reconcile_orders("BTCUSDT", datetime(2024, 1, 1))


# ---------------------------------------------------------------------------
# get_balances
# ---------------------------------------------------------------------------


class TestGetBalances:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        client = FakeBinanceClient()
        client._balances = {
            "total": {"USDT": "10000", "BTC": "1.5"},
            "free": {"USDT": "9000", "BTC": "1.5"},
            "used": {"USDT": "1000", "BTC": "0"},
        }
        adapter = _adapter(client)

        balances = await adapter.get_balances()

        assert len(balances) == 2
        usdt = next(b for b in balances if b.asset == "USDT")
        assert usdt.free == Decimal("9000")
        assert usdt.locked == Decimal("1000")
        assert usdt.total == Decimal("10000")
        assert isinstance(usdt.free, Decimal)

    @pytest.mark.anyio
    async def test_empty(self) -> None:
        client = FakeBinanceClient()
        adapter = _adapter(client)

        balances = await adapter.get_balances()
        assert balances == []

    @pytest.mark.anyio
    async def test_network_error_is_transient(self) -> None:
        client = FakeBinanceClient()
        client.fetch_balance = AsyncMock(side_effect=ccxt.NetworkError("timeout"))  # type: ignore[assignment]
        adapter = _adapter(client)

        with pytest.raises(TransientAdapterError):
            await adapter.get_balances()


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    @pytest.mark.anyio
    async def test_close_calls_client(self) -> None:
        client = FakeBinanceClient()
        adapter = _adapter(client)

        await adapter.close()
        assert client._closed is True


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_injected_client_no_keys(self) -> None:
        client = FakeBinanceClient()
        adapter = BinanceExecutionAdapter(Environment.PRODUCTION, client=client)  # type: ignore[arg-type]
        assert adapter.environment == Environment.PRODUCTION

    def test_no_client_no_keys_raises(self) -> None:
        with pytest.raises(ConfigError, match="api_key and api_secret"):
            BinanceExecutionAdapter(Environment.PRODUCTION)

    def test_testnet_sets_sandbox(self) -> None:
        client = FakeBinanceClient()
        BinanceExecutionAdapter(
            Environment.TESTNET,
            client=client,  # type: ignore[arg-type]
        )
        assert client._sandbox is True

    def test_production_no_sandbox(self) -> None:
        client = FakeBinanceClient()
        BinanceExecutionAdapter(
            Environment.PRODUCTION,
            client=client,  # type: ignore[arg-type]
        )
        assert client._sandbox is False


# ---------------------------------------------------------------------------
# F-low #2: MIN_NOTIONAL filterType fallback
# ---------------------------------------------------------------------------


class TestMarketRulesMinNotionalFallback:
    @pytest.mark.anyio
    async def test_legacy_min_notional_filter(self) -> None:
        market = _make_binance_market()
        market["info"]["filters"] = [
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.001",
                "maxQty": "1000",
                "stepSize": "0.001",
            },
            {
                "filterType": "PRICE_FILTER",
                "minPrice": "0.01",
                "maxPrice": "1000000",
                "tickSize": "0.01",
            },
            {
                "filterType": "MIN_NOTIONAL",
                "minNotional": "10",
            },
        ]
        client = FakeBinanceClient()
        client._markets = {"BTCUSDT": market}
        adapter = _adapter(client)

        rules = await adapter.get_market_rules("BTCUSDT")

        assert rules.min_notional == Decimal("10")

    @pytest.mark.anyio
    async def test_no_notional_filter_returns_zero(self) -> None:
        market = _make_binance_market()
        market["info"]["filters"] = [
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.001",
                "maxQty": "1000",
                "stepSize": "0.001",
            },
            {
                "filterType": "PRICE_FILTER",
                "minPrice": "0.01",
                "maxPrice": "1000000",
                "tickSize": "0.01",
            },
        ]
        client = FakeBinanceClient()
        client._markets = {"BTCUSDT": market}
        adapter = _adapter(client)

        rules = await adapter.get_market_rules("BTCUSDT")

        assert rules.min_notional == Decimal("0")


# ---------------------------------------------------------------------------
# F-low #3: price="0" for market orders → None
# ---------------------------------------------------------------------------


class TestMarketOrderPriceZero:
    @pytest.mark.anyio
    async def test_price_zero_becomes_none(self) -> None:
        client = FakeBinanceClient()
        client._markets = {"BTCUSDT": _make_binance_market()}
        adapter = _adapter(client)

        req = _make_request(price=None, order_type=OrderType.MARKET)
        rules = await adapter.get_market_rules("BTCUSDT")
        quantized = adapter.quantize_order(req, rules)
        ack = await adapter.place_order(quantized)

        assert ack.price is None

    @pytest.mark.anyio
    async def test_explicit_price_preserved(self) -> None:
        client = FakeBinanceClient()
        client._markets = {"BTCUSDT": _make_binance_market()}
        adapter = _adapter(client)

        req = _make_request(price="50000.0", order_type=OrderType.LIMIT)
        rules = await adapter.get_market_rules("BTCUSDT")
        quantized = adapter.quantize_order(req, rules)
        ack = await adapter.place_order(quantized)

        assert ack.price is not None
        assert ack.price > Decimal("0")

    @pytest.mark.anyio
    async def test_price_zero_string_five_decimals(self) -> None:
        """Real Binance returns '0.00000000' for market orders."""
        client = FakeBinanceClient()
        client._orders["test-001"] = {}  # prevent KeyError
        original_create = client.create_order

        async def create_with_price_00000000(**kwargs: Any) -> dict[str, Any]:
            result = await original_create(**kwargs)
            result["price"] = "0.00000000"
            return result

        client.create_order = create_with_price_00000000  # type: ignore[assignment]
        client._markets = {"BTCUSDT": _make_binance_market()}
        adapter = _adapter(client)

        req = _make_request(price=None, order_type=OrderType.MARKET)
        rules = await adapter.get_market_rules("BTCUSDT")
        quantized = adapter.quantize_order(req, rules)
        ack = await adapter.place_order(quantized)

        assert ack.price is None, f"expected None but got {ack.price!r}"


# ---------------------------------------------------------------------------
# Integration: dup-cid through ResilientExecutionAdapter (S-ADAPT-5a × S-ADAPT-3)
# ---------------------------------------------------------------------------

_DUPLICATE_CID_EXCHANGE_ERROR_MSG = (
    "binance POST https://api.binance.com/api/v3/order 400 "
    '{"code":-4116,"msg":"DUPLICATED_CLIENT_ORDER_ID"}'
)


def _fast_policy() -> RetryPolicy:
    """Fast policy for tests — minimal delays."""
    return RetryPolicy(
        max_place_attempts=2,
        max_read_attempts=3,
        base_delay_s=Decimal("0.001"),
        max_delay_s=Decimal("0.01"),
        reconcile_skew_s=5,
    )


class TestDuplicateCidResilientIntegration:
    """End-to-end: Binance dup-cid → AmbiguousExecutionError → reconcile-hit.

    Verifies that the S-ADAPT-5a dup-cid guard (AmbiguousExecutionError)
    correctly triggers the S-ADAPT-3 reconcile-before-retry flow through
    ResilientExecutionAdapter — order found by cid, no blind re-place.
    """

    @pytest.mark.anyio
    async def test_dupcid_reconcile_hit_returns_ack(self) -> None:
        """dup-cid → ambiguous → reconcile finds order → ack, no re-place."""
        client = FakeBinanceClient()
        adapter = _adapter(client)

        # 1st create_order: raises dup-cid ExchangeError (-4116)
        client.create_order = AsyncMock(
            side_effect=ccxt.ExchangeError(_DUPLICATE_CID_EXCHANGE_ERROR_MSG)
        )  # type: ignore[assignment]
        # reconcile_orders returns existing order with matching cid
        client._all_orders = [
            {
                "id": "venue-existing",
                "clientOrderId": "test-001",
                "symbol": "BTCUSDT",
                "side": "buy",
                "type": "limit",
                "amount": "0.01",
                "filled": "0",
                "price": "50000",
                "status": "open",
                "timestamp": 1700000000000,
                "trades": [],
            }
        ]

        resilient = ResilientExecutionAdapter(adapter, _fast_policy())  # type: ignore[arg-type]
        req = _make_request()

        ack = await resilient.place_order(req)

        # Reconcile found the order — returned its ack
        assert ack.client_order_id == "test-001"
        assert ack.venue_order_id == "venue-existing"
        # Only 1 create_order call (the one that raised dup-cid)
        assert len(client.create_order.call_args_list) == 1
        # 1 reconcile call (fetch_orders)
        assert len(client._all_orders) == 1  # noqa: S101

    @pytest.mark.anyio
    async def test_invalid_order_without_dup_cid_stays_terminal(self) -> None:
        """InvalidOrder WITHOUT -4116 → terminal, no reconcile."""
        client = FakeBinanceClient()
        adapter = _adapter(client)

        client.create_order = AsyncMock(
            side_effect=ccxt.InvalidOrder("LOT_SIZE filter failure")
        )  # type: ignore[assignment]

        resilient = ResilientExecutionAdapter(adapter, _fast_policy())  # type: ignore[arg-type]
        req = _make_request()

        with pytest.raises(InvalidOrderError):
            await resilient.place_order(req)

        assert len(client.create_order.call_args_list) == 1

    @pytest.mark.anyio
    async def test_exchange_error_without_dup_cid_stays_terminal(self) -> None:
        """ExchangeError WITHOUT -4116 → terminal, no reconcile."""
        client = FakeBinanceClient()
        adapter = _adapter(client)

        client.create_order = AsyncMock(
            side_effect=ccxt.ExchangeError("some other error")
        )  # type: ignore[assignment]

        resilient = ResilientExecutionAdapter(adapter, _fast_policy())  # type: ignore[arg-type]
        req = _make_request()

        with pytest.raises(OrderRejectedError):
            await resilient.place_order(req)

        assert len(client.create_order.call_args_list) == 1
