"""Tests for BybitExecutionAdapter -- offline (ccxt mocked, no network)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import ccxt.async_support as ccxt
import pytest

from clay.execution.adapter.bybit import (
    BybitExecutionAdapter,
    _is_duplicate_cid,
)
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

# ---------------------------------------------------------------------------
# FakeBybitClient -- in-memory stand-in for ccxt.bybit
# ---------------------------------------------------------------------------


class FakeBybitClient:
    """Mimics the ccxt.bybit async interface used by BybitExecutionAdapter."""

    def __init__(self) -> None:
        self._markets: dict[str, Any] = {}
        self._orders: dict[str, dict[str, Any]] = {}
        self._balances: dict[str, Any] = {"total": {}, "free": {}, "used": {}}
        self._open_orders: list[dict[str, Any]] = []
        self._all_orders: list[dict[str, Any]] = []
        self._sandbox = False
        self._demo_trading = False
        self._closed = False
        self._calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._last_params: dict[str, Any] = {}

    def set_sandbox_mode(self, enabled: bool) -> None:
        self._sandbox = enabled
        self._calls.append(("set_sandbox_mode", (enabled,), {}))

    def enable_demo_trading(self, enable: bool) -> None:
        self._demo_trading = enable
        self._calls.append(("enable_demo_trading", (enable,), {}))

    def market(self, symbol: str) -> dict[str, Any]:
        for m in self._markets.values():
            if m.get("id") == symbol or m.get("symbol") == symbol:
                return m
        raise ccxt.BadSymbol(f"bybit does not have market symbol {symbol}")

    async def load_markets(
        self, reload: bool = False, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._markets

    async def create_order(
        self,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        price: str | float | int | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._last_params = dict(params) if params else {}
        params = params or {}
        # Bybit uses clientOrderId -> orderLinkId internally
        order_id = params.get("clientOrderId", "order-1")
        response = {
            "id": order_id,
            "clientOrderId": params.get("clientOrderId", order_id),
            "symbol": symbol,
            "side": side,
            "type": type,
            "amount": str(amount),
            "price": str(price) if price else "0",
            "filled": str(amount),
            "status": "closed",
            "timestamp": 1700000000000,
            "trades": [],
        }
        self._orders[order_id] = response
        self._all_orders.append(response)
        return response

    async def cancel_order(
        self,
        id: str,
        symbol: str | None = None,  # noqa: A002
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if id not in self._orders:
            raise ccxt.OrderNotFound(f"order {id} not found")
        return {"id": id, "status": "canceled"}

    async def fetch_order(
        self,
        id: str,
        symbol: str | None = None,  # noqa: A002
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if id not in self._orders:
            raise ccxt.OrderNotFound(f"order {id} not found")
        return self._orders[id]

    async def fetch_open_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return list(self._open_orders)

    async def fetch_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return list(self._all_orders)

    async def fetch_balance(
        self, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return dict(self._balances)

    async def fetch_my_trades(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def close(self, clean_instance_data: bool = False) -> None:
        self._closed = True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_request(
    *,
    price: str | None = "50000",
    quantity: str = "0.01",
    order_type: OrderType = OrderType.LIMIT,
    client_order_id: str = "test-001",
    time_in_force: TimeInForce = TimeInForce.GTC,
    stop_price: str | None = None,
) -> OrderRequest:
    return OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=order_type,
        quantity=Decimal(quantity),
        price=Decimal(price) if price is not None else None,
        stop_price=Decimal(stop_price) if stop_price is not None else None,
        time_in_force=time_in_force,
        client_order_id=client_order_id,
    )


def _make_bybit_market() -> dict[str, Any]:
    """Return a fake Bybit market dict (ccxt-normalized, as returned by load_markets)."""
    return {
        "id": "BTCUSDT",
        "symbol": "BTC/USDT",
        "base": "BTC",
        "quote": "USDT",
        "precision": {"amount": "0.001", "price": "0.01"},
        "limits": {
            "amount": {"min": "0.001", "max": "1000"},
            "price": {"min": None, "max": None},
            "cost": {"min": "5", "max": "4000000"},
        },
        "info": {
            "lotSizeFilter": {
                "basePrecision": "0.001",
                "minOrderQty": "0.001",
                "maxOrderQty": "1000",
                "minOrderAmt": "5",
                "maxOrderAmt": "4000000",
            },
            "priceFilter": {
                "tickSize": "0.01",
            },
        },
    }


def _adapter(client: FakeBybitClient | None = None) -> BybitExecutionAdapter:
    if client is None:
        client = FakeBybitClient()
    return BybitExecutionAdapter(Environment.PRODUCTION, client=client)


# ---------------------------------------------------------------------------
# Protocol check
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_satisfies_exchange_adapter(self) -> None:
        assert isinstance(_adapter(), ExchangeAdapter)

    def test_environment_attribute(self) -> None:
        assert _adapter().environment == Environment.PRODUCTION


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_injected_client_no_keys(self) -> None:
        client = FakeBybitClient()
        adapter = BybitExecutionAdapter(Environment.PRODUCTION, client=client)
        assert adapter.environment == Environment.PRODUCTION

    def test_no_client_no_keys_raises(self) -> None:
        with pytest.raises(ConfigError, match="api_key and api_secret"):
            BybitExecutionAdapter(Environment.PRODUCTION)

    def test_testnet_sets_sandbox(self) -> None:
        client = FakeBybitClient()
        BybitExecutionAdapter(
            Environment.TESTNET,
            client=client,
        )
        assert client._sandbox is True

    def test_production_no_sandbox(self) -> None:
        client = FakeBybitClient()
        BybitExecutionAdapter(
            Environment.PRODUCTION,
            client=client,
        )
        assert client._sandbox is False

    def test_supported_order_types(self) -> None:
        adapter = _adapter()
        assert OrderType.MARKET in adapter.supported_order_types
        assert OrderType.LIMIT in adapter.supported_order_types
        assert OrderType.STOP_LIMIT in adapter.supported_order_types

    def test_supported_tif(self) -> None:
        adapter = _adapter()
        assert TimeInForce.GTC in adapter.supported_tif
        assert TimeInForce.IOC in adapter.supported_tif
        assert TimeInForce.FOK in adapter.supported_tif


# ---------------------------------------------------------------------------
# D4: Environment routing (DEMO / TESTNET / PRODUCTION / PAPER)
# ---------------------------------------------------------------------------


class TestEnvironmentRouting:
    def test_demo_enables_demo_trading(self) -> None:
        client = FakeBybitClient()
        BybitExecutionAdapter(Environment.DEMO, client=client)
        assert client._demo_trading is True
        assert client._sandbox is False
        assert any(c[0] == "enable_demo_trading" for c in client._calls)
        assert not any(c[0] == "set_sandbox_mode" for c in client._calls)

    def test_testnet_sets_sandbox(self) -> None:
        client = FakeBybitClient()
        BybitExecutionAdapter(Environment.TESTNET, client=client)
        assert client._sandbox is True
        assert client._demo_trading is False
        assert any(c[0] == "set_sandbox_mode" for c in client._calls)
        assert not any(c[0] == "enable_demo_trading" for c in client._calls)

    def test_production_no_side_effects(self) -> None:
        client = FakeBybitClient()
        BybitExecutionAdapter(Environment.PRODUCTION, client=client)
        assert client._sandbox is False
        assert client._demo_trading is False
        assert client._calls == []

    def test_paper_raises_config_error(self) -> None:
        client = FakeBybitClient()
        with pytest.raises(ConfigError, match="not supported by Bybit adapter"):
            BybitExecutionAdapter(Environment.PAPER, client=client)


# ---------------------------------------------------------------------------
# get_market_rules
# ---------------------------------------------------------------------------


class TestGetMarketRules:
    @pytest.mark.anyio
    async def test_parses_ccxt_normalized_market(self) -> None:
        client = FakeBybitClient()
        client._markets = {"BTCUSDT": _make_bybit_market()}
        adapter = _adapter(client)

        rules = await adapter.get_market_rules("BTCUSDT")

        assert rules.min_amount == Decimal("0.001")
        assert rules.max_amount == Decimal("1000")
        assert rules.min_notional == Decimal("5")
        assert rules.amount_step == Decimal("0.001")
        assert rules.price_tick == Decimal("0.01")
        assert rules.precision_mode == PrecisionMode.TICK_SIZE

    @pytest.mark.anyio
    async def test_limits_price_none_does_not_raise(self) -> None:
        """Bybit spot limits.price == None -- must not crash.

        D-23: absent upper bound → None sentinel, not Decimal("0").
        """
        client = FakeBybitClient()
        market = _make_bybit_market()
        market["limits"]["price"] = {"min": None, "max": None}
        client._markets = {"BTCUSDT": market}
        adapter = _adapter(client)

        rules = await adapter.get_market_rules("BTCUSDT")

        # min_price: lower bound, None → Decimal("0") via _dec
        assert rules.min_price == Decimal("0")
        # max_price: upper bound, None → None sentinel (D-23)
        assert rules.max_price is None

    @pytest.mark.anyio
    async def test_limits_amount_max_none_returns_sentinel(self) -> None:
        """Bybit limits.amount.max == None → D-23 None sentinel."""
        client = FakeBybitClient()
        market = _make_bybit_market()
        market["limits"]["amount"] = {"min": Decimal("0.001"), "max": None}
        client._markets = {"BTCUSDT": market}
        adapter = _adapter(client)

        rules = await adapter.get_market_rules("BTCUSDT")

        # min_amount: lower bound, present → Decimal
        assert rules.min_amount == Decimal("0.001")
        # max_amount: upper bound, None → None sentinel (D-23)
        assert rules.max_amount is None

    @pytest.mark.anyio
    async def test_unknown_symbol_raises(self) -> None:
        client = FakeBybitClient()
        client._markets = {}
        adapter = _adapter(client)

        with pytest.raises(InvalidOrderError, match="unknown symbol"):
            await adapter.get_market_rules("NONEXIST")

    @pytest.mark.anyio
    async def test_network_error_is_transient(self) -> None:
        client = FakeBybitClient()
        client.load_markets = AsyncMock(side_effect=ccxt.NetworkError("timeout"))
        adapter = _adapter(client)

        with pytest.raises(TransientAdapterError):
            await adapter.get_market_rules("BTCUSDT")

    @pytest.mark.anyio
    async def test_auth_error_is_config(self) -> None:
        client = FakeBybitClient()
        client.load_markets = AsyncMock(side_effect=ccxt.AuthenticationError("bad"))
        adapter = _adapter(client)

        with pytest.raises(ConfigError):
            await adapter.get_market_rules("BTCUSDT")


# ---------------------------------------------------------------------------
# place_order
# ---------------------------------------------------------------------------


class TestPlaceOrder:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        client = FakeBybitClient()
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
    async def test_client_order_id_in_params(self) -> None:
        """clientOrderId must be passed to create_order params."""
        client = FakeBybitClient()
        adapter = _adapter(client)
        req = _make_request(client_order_id="my- cid-123")

        ack = await adapter.place_order(req)

        # FakeBybitClient stores clientOrderId as the order id
        assert ack.client_order_id == "my- cid-123"

    @pytest.mark.anyio
    async def test_insufficient_funds_error(self) -> None:
        client = FakeBybitClient()
        client.create_order = AsyncMock(side_effect=ccxt.InsufficientFunds("no funds"))
        adapter = _adapter(client)

        with pytest.raises(InsufficientFundsError):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_invalid_order_error(self) -> None:
        client = FakeBybitClient()
        client.create_order = AsyncMock(side_effect=ccxt.InvalidOrder("bad qty"))
        adapter = _adapter(client)

        with pytest.raises(InvalidOrderError):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_network_error_is_ambiguous(self) -> None:
        client = FakeBybitClient()
        client.create_order = AsyncMock(side_effect=ccxt.NetworkError("timeout"))
        adapter = _adapter(client)

        with pytest.raises(AmbiguousExecutionError):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_exchange_error_is_rejected(self) -> None:
        client = FakeBybitClient()
        client.create_order = AsyncMock(side_effect=ccxt.ExchangeError("generic"))
        adapter = _adapter(client)

        with pytest.raises(OrderRejectedError):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_auth_error_is_config(self) -> None:
        client = FakeBybitClient()
        client.create_order = AsyncMock(side_effect=ccxt.AuthenticationError("bad key"))
        adapter = _adapter(client)

        with pytest.raises(ConfigError):
            await adapter.place_order(_make_request())


class TestStopLimit:
    """D-6x: Bybit spot STOP_LIMIT — эмуляция через unified triggerPrice.

    ccxt для spot сам ставит orderFilter='StopOrder' при наличии
    triggerPrice (ccxt/bybit.py:4040-4041, 4111); triggerDirection для
    spot не поддерживается (4104-4106).
    """

    @pytest.mark.anyio
    async def test_stop_limit_with_price(self) -> None:
        """STOP_LIMIT → type='limit', params['triggerPrice']=str(stop_price)."""
        client = FakeBybitClient()
        adapter = _adapter(client)
        req = _make_request(
            order_type=OrderType.STOP_LIMIT,
            price="51000",
            stop_price="49000",
            client_order_id="stop-001",
        )

        ack = await adapter.place_order(req)

        assert ack.client_order_id == "stop-001"
        assert client._last_params["clientOrderId"] == "stop-001"
        assert client._last_params["triggerPrice"] == "49000"

    @pytest.mark.anyio
    async def test_stop_limit_without_price(self) -> None:
        """STOP_LIMIT без stop_price → InvalidOrderError, сеть не вызвана."""
        client = FakeBybitClient()
        adapter = _adapter(client)
        req = _make_request(order_type=OrderType.STOP_LIMIT, price="51000")

        with pytest.raises(InvalidOrderError, match="stop_price"):
            await adapter.place_order(req)
        assert client._all_orders == []

    @pytest.mark.anyio
    async def test_stop_price_is_string_not_float(self) -> None:
        """Stop-цена уходит строкой (не float) — не теряем точность Decimal."""
        client = FakeBybitClient()
        adapter = _adapter(client)
        req = _make_request(
            order_type=OrderType.STOP_LIMIT,
            price="51000.0000000001",
            stop_price="49000.1234567890123456789",
        )

        await adapter.place_order(req)

        assert client._last_params["triggerPrice"] == "49000.1234567890123456789"
        assert isinstance(client._last_params["triggerPrice"], str)

    def test_stop_limit_in_supported_order_types(self) -> None:
        """STOP_LIMIT входит в supported_order_types."""
        adapter = _adapter()
        assert OrderType.STOP_LIMIT in adapter.supported_order_types


# ---------------------------------------------------------------------------
# _is_duplicate_cid (unit)
# ---------------------------------------------------------------------------


class TestIsDuplicateCid:
    def test_spot_error_code_12141(self) -> None:
        assert _is_duplicate_cid(ccxt.BadRequest("bybit 12141 Duplicate clientOrderId"))

    def test_linear_error_code_170141(self) -> None:
        assert _is_duplicate_cid(
            ccxt.InvalidOrder("bybit 170141 Duplicate clientOrderId")
        )

    def test_code_only_12141(self) -> None:
        assert _is_duplicate_cid(ccxt.BadRequest("12141"))

    def test_code_only_170141(self) -> None:
        assert _is_duplicate_cid(ccxt.InvalidOrder("170141"))

    def test_unrelated_exchange_error(self) -> None:
        assert not _is_duplicate_cid(ccxt.ExchangeError("generic error"))

    def test_unrelated_invalid_order(self) -> None:
        assert not _is_duplicate_cid(ccxt.InvalidOrder("Insufficient balance"))

    def test_empty_message(self) -> None:
        assert not _is_duplicate_cid(ccxt.ExchangeError(""))


# ---------------------------------------------------------------------------
# place_order: duplicate clientOrderId -> AmbiguousExecutionError
# ---------------------------------------------------------------------------


_DUPLICATE_CID_SPOT_MSG = (
    "bybit POST https://api.bybit.com/v5/order 400 "
    '{"retCode":12141,"retMsg":"Duplicate clientOrderId"}'
)
_DUPLICATE_CID_LINEAR_MSG = (
    "bybit POST https://api.bybit.com/v5/order 400 "
    '{"retCode":170141,"retMsg":"Duplicate clientOrderId"}'
)


class TestPlaceOrderDuplicateCid:
    """Duplicate clientOrderId must raise AmbiguousExecutionError, not terminal."""

    @pytest.mark.anyio
    async def test_spot_bad_request_is_ambiguous(self) -> None:
        """Bybit Spot maps 12141 -> BadRequest."""
        client = FakeBybitClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.BadRequest(_DUPLICATE_CID_SPOT_MSG)
        )
        adapter = _adapter(client)

        with pytest.raises(AmbiguousExecutionError, match="12141"):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_linear_invalid_order_is_ambiguous(self) -> None:
        """Bybit Linear maps 170141 -> InvalidOrder -- still ambiguous."""
        client = FakeBybitClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.InvalidOrder(_DUPLICATE_CID_LINEAR_MSG)
        )
        adapter = _adapter(client)

        with pytest.raises(AmbiguousExecutionError, match="170141"):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_cid_preserved_in_message(self) -> None:
        """AmbiguousExecutionError includes the client_order_id."""
        client = FakeBybitClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.BadRequest(_DUPLICATE_CID_SPOT_MSG)
        )
        adapter = _adapter(client)

        with pytest.raises(AmbiguousExecutionError, match="cid='test-001'"):
            await adapter.place_order(_make_request(client_order_id="test-001"))

    @pytest.mark.anyio
    async def test_invalid_order_without_dup_cid_stays_terminal(self) -> None:
        """InvalidOrder WITHOUT 12141/170141 must still raise InvalidOrderError."""
        client = FakeBybitClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.InvalidOrder("Insufficient balance")
        )
        adapter = _adapter(client)

        with pytest.raises(InvalidOrderError):
            await adapter.place_order(_make_request())

    @pytest.mark.anyio
    async def test_exchange_error_without_dup_cid_stays_rejected(self) -> None:
        """ExchangeError WITHOUT 12141/170141 must still raise OrderRejectedError."""
        client = FakeBybitClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.ExchangeError("some other error")
        )
        adapter = _adapter(client)

        with pytest.raises(OrderRejectedError):
            await adapter.place_order(_make_request())


# ---------------------------------------------------------------------------
# D4-regression: message contains actual venue error, not hardcoded code
# ---------------------------------------------------------------------------


class TestDuplicateCidMessageRegression:
    """Verify AmbiguousExecutionError message contains venue error text."""

    @pytest.mark.anyio
    async def test_linear_170141_not_fake_12141(self) -> None:
        """170141 error → message contains '170141', cid=, NOT '12141'."""
        client = FakeBybitClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.InvalidOrder(_DUPLICATE_CID_LINEAR_MSG)
        )
        adapter = _adapter(client)

        with pytest.raises(AmbiguousExecutionError, match="170141") as exc_info:
            await adapter.place_order(_make_request())
        msg = str(exc_info.value)
        assert "cid=" in msg
        assert "12141" not in msg

    @pytest.mark.anyio
    async def test_spot_12141_still_ambiguous(self) -> None:
        """12141 path still raises AmbiguousExecutionError (regression guard)."""
        client = FakeBybitClient()
        client.create_order = AsyncMock(
            side_effect=ccxt.InvalidOrder(_DUPLICATE_CID_SPOT_MSG)
        )
        adapter = _adapter(client)

        with pytest.raises(AmbiguousExecutionError, match="12141"):
            await adapter.place_order(_make_request())


# ---------------------------------------------------------------------------
# cancel_order / get_order / get_open_orders / reconcile / balances / close
# ---------------------------------------------------------------------------


class TestCancelOrder:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        client = FakeBybitClient()
        client._orders["o-1"] = {"id": "o-1"}
        adapter = _adapter(client)

        result = await adapter.cancel_order("BTCUSDT", "o-1")
        assert result == CancelResult.CANCELED

    @pytest.mark.anyio
    async def test_order_not_found_returns_not_found(self) -> None:
        client = FakeBybitClient()
        adapter = _adapter(client)

        result = await adapter.cancel_order("BTCUSDT", "nonexistent")
        assert result == CancelResult.NOT_FOUND

    @pytest.mark.anyio
    async def test_network_error_is_transient(self) -> None:
        client = FakeBybitClient()
        client.cancel_order = AsyncMock(side_effect=ccxt.NetworkError("timeout"))
        adapter = _adapter(client)

        with pytest.raises(TransientAdapterError):
            await adapter.cancel_order("BTCUSDT", "o-1")


class TestGetOrder:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        client = FakeBybitClient()
        client._orders["o-1"] = {
            "id": "o-1",
            "clientOrderId": "cid-1",
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

        snap = await adapter.get_order("BTCUSDT", "o-1")

        assert snap.venue_order_id == "o-1"
        assert snap.client_order_id == "cid-1"

    @pytest.mark.anyio
    async def test_not_found_raises_order_not_found(self) -> None:
        client = FakeBybitClient()
        adapter = _adapter(client)

        with pytest.raises(OrderNotFoundError) as exc_info:
            await adapter.get_order("BTCUSDT", "nonexistent")

        assert exc_info.value.venue_order_id == "nonexistent"
        assert exc_info.value.symbol == "BTCUSDT"

    @pytest.mark.anyio
    async def test_network_error_is_transient(self) -> None:
        client = FakeBybitClient()
        client.fetch_order = AsyncMock(side_effect=ccxt.NetworkError("timeout"))
        adapter = _adapter(client)

        with pytest.raises(TransientAdapterError):
            await adapter.get_order("BTCUSDT", "o-1")


class TestGetOpenOrders:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        client = FakeBybitClient()
        client._open_orders = [{"id": "o-1", "symbol": "BTCUSDT", "status": "open"}]
        adapter = _adapter(client)

        orders = await adapter.get_open_orders("BTCUSDT")
        assert len(orders) == 1

    @pytest.mark.anyio
    async def test_empty(self) -> None:
        client = FakeBybitClient()
        adapter = _adapter(client)

        orders = await adapter.get_open_orders("BTCUSDT")
        assert orders == []


class TestReconcileOrders:
    @pytest.mark.anyio
    async def test_calls_fetch_orders(self) -> None:
        client = FakeBybitClient()
        adapter = _adapter(client)

        from datetime import datetime, timezone

        orders = await adapter.reconcile_orders(
            "BTCUSDT", datetime(2024, 1, 1, tzinfo=timezone.utc)
        )
        assert isinstance(orders, list)


class TestGetBalances:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        client = FakeBybitClient()
        client._balances = {
            "total": {"BTC": "1.5", "USDT": "10000"},
            "free": {"BTC": "1.0", "USDT": "5000"},
            "used": {"BTC": "0.5", "USDT": "5000"},
        }
        adapter = _adapter(client)

        balances = await adapter.get_balances()

        assert len(balances) == 2
        btc = next(b for b in balances if b.asset == "BTC")
        assert btc.free == Decimal("1.0")
        assert btc.locked == Decimal("0.5")
        assert btc.total == Decimal("1.5")

    @pytest.mark.anyio
    async def test_empty(self) -> None:
        client = FakeBybitClient()
        adapter = _adapter(client)

        balances = await adapter.get_balances()
        assert balances == []


class TestClose:
    @pytest.mark.anyio
    async def test_close_calls_client(self) -> None:
        client = FakeBybitClient()
        adapter = _adapter(client)

        await adapter.close()
        assert client._closed is True


# ---------------------------------------------------------------------------
# D7.2: Bybit._extract_client_order_id — orderLinkId priority
# ---------------------------------------------------------------------------


class TestExtractClientOrderId:
    def test_info_orderlinkid_has_priority(self) -> None:
        """info.orderLinkId has priority over empty unified clientOrderId."""
        client = FakeBybitClient()
        adapter = _adapter(client)

        response = {
            "clientOrderId": "",
            "info": {"orderLinkId": "my-order-link-001"},
        }
        result = adapter._extract_client_order_id(response)
        assert result == "my-order-link-001"

    def test_fallback_to_clientOrderId(self) -> None:
        """When info is absent, falls back to unified clientOrderId."""
        client = FakeBybitClient()
        adapter = _adapter(client)

        response = {
            "clientOrderId": "unified-cid-002",
        }
        result = adapter._extract_client_order_id(response)
        assert result == "unified-cid-002"

    def test_info_empty_dict_fallback(self) -> None:
        """info is empty dict → falls back to clientOrderId."""
        client = FakeBybitClient()
        adapter = _adapter(client)

        response = {
            "clientOrderId": "fallback-cid",
            "info": {},
        }
        result = adapter._extract_client_order_id(response)
        assert result == "fallback-cid"

    def test_both_empty_returns_empty(self) -> None:
        """Both info.orderLinkId and clientOrderId empty → returns empty string."""
        client = FakeBybitClient()
        adapter = _adapter(client)

        response = {
            "clientOrderId": "",
            "info": {"orderLinkId": ""},
        }
        result = adapter._extract_client_order_id(response)
        assert result == ""


# ---------------------------------------------------------------------------
# S-TIF-1: timeInForce reaches create_order params (Bybit)
# ---------------------------------------------------------------------------


class TestTimeInForceDelivery:
    """D-36: time_in_force must arrive in create_order params for Bybit."""

    @pytest.mark.anyio
    async def test_t6_limit_ioc(self) -> None:
        """T6 LIMIT + IOC → timeInForce == 'IOC' and clientOrderId present."""
        client = FakeBybitClient()
        adapter = _adapter(client)
        req = _make_request(time_in_force=TimeInForce.IOC)

        await adapter.place_order(req)

        assert client._last_params["timeInForce"] == "IOC"
        assert "clientOrderId" in client._last_params

    @pytest.mark.anyio
    async def test_t7_limit_fok(self) -> None:
        """T7 LIMIT + FOK → timeInForce == 'FOK'."""
        client = FakeBybitClient()
        adapter = _adapter(client)
        req = _make_request(time_in_force=TimeInForce.FOK)

        await adapter.place_order(req)

        assert client._last_params["timeInForce"] == "FOK"

    @pytest.mark.anyio
    async def test_t8_market_gtc_omits_tif(self) -> None:
        """T8 MARKET + GTC → key 'timeInForce' must NOT be in params."""
        client = FakeBybitClient()
        adapter = _adapter(client)
        req = _make_request(order_type=OrderType.MARKET, time_in_force=TimeInForce.GTC)

        await adapter.place_order(req)

        assert "timeInForce" not in client._last_params
