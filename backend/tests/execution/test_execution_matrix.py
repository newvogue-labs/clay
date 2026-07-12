"""D9 test-matrix: comprehensive mocked-ccxt coverage for execution layer (S-LIVE-5).

Test-only slice — no src changes. All ccxt calls mocked, no network.
Parametrizes BinanceTestnetExecutionClient + LiveExecutionClient (code-twins).
"""

from unittest.mock import AsyncMock  # noqa: F401 — used in conftest

import ccxt.async_support as ccxt
import pytest

from clay.execution.binance_testnet import (
    BinanceTestnetExecutionClient,
    DryRunExecutionClient,
    LiveExecutionClient,
)
from clay.execution.exceptions import (
    ExecutionConfigError,
    OrderRejectedError,
    OrderTimeoutError,
    PartialFillError,
)
from clay.execution.factory import build_execution_client


# ── helpers ───────────────────────────────────────────────────────────


def _make_response(**overrides) -> dict:
    base = {
        "id": "123",
        "clientOrderId": "cid-1",
        "symbol": "BTCUSDT",
        "side": "buy",
        "amount": 0.01,
        "price": 50000.0,
        "status": "FILLED",
        "timestamp": 1_700_000_000_000,
        "filled": 0.01,
        "trades": [],
    }
    base.update(overrides)
    return base


def _make_filled_response(**overrides) -> dict:
    return _make_response(
        trades=[
            {
                "id": "t1",
                "amount": 0.01,
                "price": 50000.0,
                "commission": 0.00001,
                "commissionAsset": "BNB",
                "timestamp": 1_700_000_000_000,
            }
        ],
        **overrides,
    )


def _build_client(cls, mock_ccxt, monkeypatch, **kwargs):
    mock_cls, mock_instance = mock_ccxt
    monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
    return cls(api_key="k", api_secret="s", **kwargs)


# ══════════════════════════════════════════════════════════════════════
# D2 — place_order matrix (parametrized Testnet + Live)
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture(
    params=[
        (BinanceTestnetExecutionClient, "testnet"),
        (LiveExecutionClient, "binance_live"),
    ],
    ids=["testnet", "live"],
)
def real_client(request, mock_ccxt, monkeypatch):
    cls, source = request.param
    client = _build_client(cls, mock_ccxt, monkeypatch)
    _, mock_instance = mock_ccxt
    assert client.source == source
    return client, mock_instance


class TestPlaceOrderMatrix:
    def test_happy_full_fill_with_fills(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.create_order.return_value = _make_filled_response()
        import asyncio

        result = asyncio.run(client.place_order("BTCUSDT", "buy", 0.01, "MARKET"))
        assert result.exchange_order_id == "123"
        assert result.symbol == "BTCUSDT"
        assert result.status == "FILLED"
        assert len(result.fills) == 1
        assert result.fills[0].trade_id == "t1"

    def test_happy_no_trades(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.create_order.return_value = _make_response(
            trades=[], filled=0.5, amount=0.5
        )
        import asyncio

        result = asyncio.run(
            client.place_order("BTCUSDT", "sell", 0.5, "LIMIT", price=60000.0)
        )
        assert result.exchange_order_id == "123"
        assert result.fills == []

    def test_partial_fill_raises(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.create_order.return_value = _make_response(
            filled=0.005, status="PARTIALLY_FILLED"
        )
        import asyncio

        with pytest.raises(PartialFillError, match="partial fill"):
            asyncio.run(client.place_order("BTCUSDT", "buy", 0.01, "MARKET"))

    def test_filled_zero_no_error(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.create_order.return_value = _make_response(filled=0.0)
        import asyncio

        result = asyncio.run(client.place_order("BTCUSDT", "buy", 0.01, "MARKET"))
        assert result.exchange_order_id == "123"

    def test_filled_equals_quantity_no_error(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.create_order.return_value = _make_response(filled=0.01)
        import asyncio

        result = asyncio.run(client.place_order("BTCUSDT", "buy", 0.01, "MARKET"))
        assert result.exchange_order_id == "123"

    def test_client_order_id_passthrough(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.create_order.return_value = _make_response(clientOrderId="my-cid")
        import asyncio

        result = asyncio.run(
            client.place_order(
                "BTCUSDT", "buy", 0.01, "MARKET", client_order_id="my-cid"
            )
        )
        assert result.client_order_id == "my-cid"

    def test_stop_price_in_params(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.create_order.return_value = _make_response()
        import asyncio

        asyncio.run(
            client.place_order(
                "BTCUSDT",
                "buy",
                0.01,
                "STOP_LOSS_LIMIT",
                price=50000.0,
                stop_price=49000.0,
            )
        )
        call_kwargs = mock_inst.create_order.call_args
        assert call_kwargs[1]["params"].get("stopPrice") == 49000.0

    # ── error-translation ─────────────────────────────────────────────

    def test_insufficient_funds(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.create_order.side_effect = ccxt.InsufficientFunds("nope")
        import asyncio

        with pytest.raises(OrderRejectedError, match="insufficient funds"):
            asyncio.run(client.place_order("BTCUSDT", "buy", 100.0, "MARKET"))

    def test_invalid_order(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.create_order.side_effect = ccxt.InvalidOrder("bad")
        import asyncio

        with pytest.raises(OrderRejectedError, match="invalid order"):
            asyncio.run(client.place_order("BTCUSDT", "buy", 0.01, "MARKET"))

    def test_network_error(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.create_order.side_effect = ccxt.NetworkError("timeout")
        import asyncio

        with pytest.raises(OrderTimeoutError, match="network error"):
            asyncio.run(client.place_order("BTCUSDT", "buy", 0.01, "MARKET"))

    def test_exchange_error(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.create_order.side_effect = ccxt.ExchangeError("generic")
        import asyncio

        with pytest.raises(OrderRejectedError, match="generic"):
            asyncio.run(client.place_order("BTCUSDT", "buy", 0.01, "MARKET"))

    # ── notional guard wiring ─────────────────────────────────────────

    def test_guard_cap_zero_passes(self, mock_ccxt, monkeypatch) -> None:
        client = _build_client(
            BinanceTestnetExecutionClient,
            mock_ccxt,
            monkeypatch,
            max_order_notional_usdt=0.0,
        )
        _, mock_inst = mock_ccxt
        mock_inst.create_order.return_value = _make_response(
            filled=1000.0, amount=1000.0
        )
        import asyncio

        result = asyncio.run(
            client.place_order("BTCUSDT", "buy", 1000.0, "MARKET", price=100000.0)
        )
        assert result.exchange_order_id == "123"

    def test_guard_over_cap_rejects_before_ccxt(self, mock_ccxt, monkeypatch) -> None:
        client = _build_client(
            LiveExecutionClient,
            mock_ccxt,
            monkeypatch,
            max_order_notional_usdt=50.0,
        )
        _, mock_inst = mock_ccxt
        import asyncio

        with pytest.raises(OrderRejectedError, match="exceeds cap"):
            asyncio.run(
                client.place_order("BTCUSDT", "buy", 0.01, "MARKET", price=100000.0)
            )
        mock_inst.create_order.assert_not_called()

    def test_guard_market_order_missing_price_fails_closed(
        self, mock_ccxt, monkeypatch
    ) -> None:
        client = _build_client(
            BinanceTestnetExecutionClient,
            mock_ccxt,
            monkeypatch,
            max_order_notional_usdt=50.0,
        )
        _, mock_inst = mock_ccxt
        import asyncio

        with pytest.raises(OrderRejectedError, match="price is unknown"):
            asyncio.run(
                client.place_order("BTCUSDT", "buy", 0.01, "MARKET", price=None)
            )
        mock_inst.create_order.assert_not_called()

    def test_guard_under_cap_allows(self, mock_ccxt, monkeypatch) -> None:
        client = _build_client(
            LiveExecutionClient,
            mock_ccxt,
            monkeypatch,
            max_order_notional_usdt=50.0,
        )
        _, mock_inst = mock_ccxt
        mock_inst.create_order.return_value = _make_response(
            filled=0.0001, amount=0.0001
        )
        mock_inst.create_order.return_value = _make_response()
        import asyncio

        result = asyncio.run(
            client.place_order("BTCUSDT", "buy", 0.0001, "MARKET", price=100000.0)
        )
        assert result.exchange_order_id == "123"


# ══════════════════════════════════════════════════════════════════════
# D3 — query / cancel / balances / trades
# ══════════════════════════════════════════════════════════════════════


class TestCancelOrder:
    def test_happy(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.cancel_order.return_value = {
            "id": "456",
            "clientOrderId": "cid-2",
            "status": "canceled",
        }
        import asyncio

        result = asyncio.run(client.cancel_order("BTCUSDT", "456"))
        assert result.exchange_order_id == "456"
        assert result.status == "canceled"

    def test_not_found(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.cancel_order.side_effect = ccxt.OrderNotFound("gone")
        import asyncio

        result = asyncio.run(client.cancel_order("BTCUSDT", "404"))
        assert result.status == "not_found"
        assert result.exchange_order_id == "404"

    def test_exchange_error(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.cancel_order.side_effect = ccxt.ExchangeError("fail")
        import asyncio

        with pytest.raises(OrderRejectedError, match="fail"):
            asyncio.run(client.cancel_order("BTCUSDT", "123"))


class TestGetOrderStatus:
    def test_happy(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.fetch_order.return_value = {
            "id": "789",
            "clientOrderId": "cid-3",
            "symbol": "BTCUSDT",
            "side": "sell",
            "type": "LIMIT",
            "status": "FILLED",
            "amount": 0.02,
            "filled": 0.02,
            "price": 55000.0,
            "timestamp": 1_700_000_000_000,
        }
        import asyncio

        status = asyncio.run(client.get_order_status("BTCUSDT", "789"))
        assert status.exchange_order_id == "789"
        assert status.status == "FILLED"
        assert status.executed_qty == 0.02

    def test_not_found(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.fetch_order.side_effect = ccxt.OrderNotFound("missing")
        import asyncio

        status = asyncio.run(client.get_order_status("BTCUSDT", "404"))
        assert status.status == "not_found"
        assert status.executed_qty == 0.0

    def test_exchange_error(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.fetch_order.side_effect = ccxt.ExchangeError("err")
        import asyncio

        with pytest.raises(OrderRejectedError):
            asyncio.run(client.get_order_status("BTCUSDT", "123"))


class TestGetOpenOrders:
    def test_list_mapping(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.fetch_open_orders.return_value = [
            {"id": "o1", "symbol": "BTCUSDT", "status": "open"},
            {"id": "o2", "symbol": "ETHUSDT", "status": "open"},
        ]
        import asyncio

        orders = asyncio.run(client.get_open_orders())
        assert len(orders) == 2
        assert orders[0].exchange_order_id == "o1"

    def test_exchange_error(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.fetch_open_orders.side_effect = ccxt.ExchangeError("err")
        import asyncio

        with pytest.raises(OrderRejectedError):
            asyncio.run(client.get_open_orders())


class TestGetBalances:
    def test_mapping(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.fetch_balance.return_value = {
            "total": {"BTC": 1.5, "USDT": 10000.0},
            "free": {"BTC": 1.0, "USDT": 5000.0},
            "used": {"BTC": 0.5, "USDT": 5000.0},
        }
        import asyncio

        balances = asyncio.run(client.get_balances())
        assert len(balances) == 2
        btc = [b for b in balances if b.asset == "BTC"][0]
        assert btc.total == 1.5
        assert btc.free == 1.0
        assert btc.locked == 0.5

    def test_auth_error(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.fetch_balance.side_effect = ccxt.AuthenticationError("bad key")
        import asyncio

        with pytest.raises(ExecutionConfigError, match="auth failed"):
            asyncio.run(client.get_balances())

    def test_exchange_error(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.fetch_balance.side_effect = ccxt.ExchangeError("err")
        import asyncio

        with pytest.raises(OrderRejectedError):
            asyncio.run(client.get_balances())


class TestGetRecentTrades:
    def test_mapping(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.fetch_my_trades.return_value = [
            {
                "id": "t1",
                "order": "o1",
                "side": "buy",
                "amount": 0.01,
                "price": 50000.0,
                "fee": {"cost": 0.005, "currency": "USDT"},
                "timestamp": 1_700_000_000_000,
            }
        ]
        import asyncio

        trades = asyncio.run(client.get_recent_trades("BTCUSDT"))
        assert len(trades) == 1
        assert trades[0].trade_id == "t1"
        assert trades[0].commission == 0.005

    def test_auth_error(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.fetch_my_trades.side_effect = ccxt.AuthenticationError("bad")
        import asyncio

        with pytest.raises(ExecutionConfigError, match="auth failed"):
            asyncio.run(client.get_recent_trades("BTCUSDT"))

    def test_exchange_error(self, real_client) -> None:
        client, mock_inst = real_client
        mock_inst.fetch_my_trades.side_effect = ccxt.ExchangeError("err")
        import asyncio

        with pytest.raises(OrderRejectedError):
            asyncio.run(client.get_recent_trades("BTCUSDT"))


# ══════════════════════════════════════════════════════════════════════
# D4 — DryRun + construction
# ══════════════════════════════════════════════════════════════════════


class TestDryRunClient:
    def test_place_order_returns_dry_run(self) -> None:
        client = DryRunExecutionClient()
        import asyncio

        result = asyncio.run(client.place_order("BTCUSDT", "buy", 0.01, "MARKET"))
        assert result.status == "dry_run"
        assert result.exchange_order_id == ""

    def test_place_order_with_kwargs(self) -> None:
        client = DryRunExecutionClient()
        import asyncio

        result = asyncio.run(
            client.place_order(
                "ETHUSDT",
                "sell",
                1.0,
                "LIMIT",
                price=3000.0,
                client_order_id="dry-cid",
            )
        )
        assert result.status == "dry_run"
        assert result.client_order_id == "dry-cid"

    def test_cancel_order(self) -> None:
        client = DryRunExecutionClient()
        import asyncio

        result = asyncio.run(client.cancel_order("BTCUSDT", "123"))
        assert result.status == "dry_run"

    def test_get_order_status(self) -> None:
        client = DryRunExecutionClient()
        import asyncio

        result = asyncio.run(client.get_order_status("BTCUSDT", "123"))
        assert result.status == "dry_run"

    def test_get_open_orders_empty(self) -> None:
        client = DryRunExecutionClient()
        import asyncio

        assert asyncio.run(client.get_open_orders()) == []

    def test_get_balances_empty(self) -> None:
        client = DryRunExecutionClient()
        import asyncio

        assert asyncio.run(client.get_balances()) == []

    def test_get_recent_trades_empty(self) -> None:
        client = DryRunExecutionClient()
        import asyncio

        assert asyncio.run(client.get_recent_trades("BTCUSDT")) == []

    def test_source_label(self) -> None:
        assert DryRunExecutionClient.source == "dry_run"


class TestConstruction:
    def test_testnet_missing_keys(self) -> None:
        with pytest.raises(ExecutionConfigError, match="required"):
            BinanceTestnetExecutionClient(api_key="", api_secret="")

    def test_live_missing_keys(self) -> None:
        with pytest.raises(ExecutionConfigError, match="required"):
            LiveExecutionClient(api_key="", api_secret="")

    def test_testnet_sandbox_mode(self, mock_ccxt, monkeypatch) -> None:
        _build_client(BinanceTestnetExecutionClient, mock_ccxt, monkeypatch)
        _, mock_inst = mock_ccxt
        mock_inst.set_sandbox_mode.assert_called_once_with(True)

    def test_live_no_sandbox_mode(self, mock_ccxt, monkeypatch) -> None:
        _build_client(LiveExecutionClient, mock_ccxt, monkeypatch)
        _, mock_inst = mock_ccxt
        mock_inst.set_sandbox_mode.assert_not_called()


# ══════════════════════════════════════════════════════════════════════
# D5 — factory matrix
# ══════════════════════════════════════════════════════════════════════


class TestFactoryMatrix:
    def test_dry_run(self) -> None:
        client = build_execution_client(mode="dry_run")
        assert client.source == "dry_run"

    def test_testnet_with_creds(self) -> None:
        client = build_execution_client(mode="testnet", api_key="k", api_secret="s")
        assert client.source == "testnet"

    def test_testnet_missing_creds(self, monkeypatch) -> None:
        monkeypatch.delenv("CLAY_BINANCE_TESTNET_API_KEY", raising=False)
        monkeypatch.delenv("CLAY_BINANCE_TESTNET_API_SECRET", raising=False)
        with pytest.raises(ExecutionConfigError, match="required"):
            build_execution_client(mode="testnet")

    def test_live_with_creds(self) -> None:
        client = build_execution_client(mode="live", api_key="lk", api_secret="ls")
        assert client.source == "binance_live"

    def test_live_missing_creds(self, monkeypatch) -> None:
        monkeypatch.delenv("CLAY_BINANCE_LIVE_API_KEY", raising=False)
        monkeypatch.delenv("CLAY_BINANCE_LIVE_API_SECRET", raising=False)
        with pytest.raises(ExecutionConfigError, match="required"):
            build_execution_client(mode="live")

    def test_unknown_mode(self) -> None:
        with pytest.raises(ExecutionConfigError, match="Unknown"):
            build_execution_client(mode="turbo")

    def test_max_notional_passthrough(self) -> None:
        client = build_execution_client(
            mode="testnet",
            api_key="k",
            api_secret="s",
            max_order_notional_usdt=100.0,
        )
        assert client._max_order_notional_usdt == 100.0  # type: ignore[reportAttributeAccessIssue]

    def test_recv_window_passthrough(self) -> None:
        client = build_execution_client(
            mode="testnet",
            api_key="k",
            api_secret="s",
            recv_window=10000,
        )
        assert client._client.options["recvWindow"] == 10000  # type: ignore[reportAttributeAccessIssue]
