"""Tests for LiveExecutionClient (mocked ccxt) and guard wiring."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from clay.execution.binance_testnet import LiveExecutionClient
from clay.execution.exceptions import OrderRejectedError
from clay.execution.factory import build_execution_client


@pytest.fixture
def mock_ccxt():
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.close = AsyncMock()
    mock_instance.create_order = AsyncMock()
    mock_instance.cancel_order = AsyncMock()
    mock_instance.fetch_order = AsyncMock()
    mock_instance.fetch_open_orders = AsyncMock()
    mock_instance.fetch_balance = AsyncMock()
    mock_instance.fetch_my_trades = AsyncMock()
    mock_cls.return_value = mock_instance
    return mock_cls, mock_instance


def test_live_client_source() -> None:
    client = LiveExecutionClient(api_key="k", api_secret="s")
    assert client.source == "binance_live"


def test_live_client_no_sandbox_mode(
    mock_ccxt, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_cls, mock_instance = mock_ccxt
    monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
    LiveExecutionClient(api_key="k", api_secret="s")
    mock_instance.set_sandbox_mode.assert_not_called()


def test_live_client_place_order_success(
    mock_ccxt, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_cls, mock_instance = mock_ccxt
    monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
    client = LiveExecutionClient(api_key="k", api_secret="s")
    mock_instance.create_order.return_value = {
        "id": "456",
        "clientOrderId": "lc-1",
        "symbol": "BTCUSDT",
        "side": "buy",
        "amount": 0.01,
        "price": 50000.0,
        "status": "FILLED",
        "timestamp": 1_700_000_000_000,
        "filled": 0.01,
        "trades": [],
    }

    async def run() -> None:
        result = await client.place_order(
            "BTCUSDT", "buy", 0.01, "MARKET", client_order_id="lc-1"
        )
        assert result.exchange_order_id == "456"
        assert result.client_order_id == "lc-1"

    import asyncio

    asyncio.run(run())


def test_live_client_insufficient_funds(
    mock_ccxt, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ccxt.async_support as ccxt_mod

    mock_cls, mock_instance = mock_ccxt
    monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
    client = LiveExecutionClient(api_key="k", api_secret="s")
    mock_instance.create_order.side_effect = ccxt_mod.InsufficientFunds("no funds")

    async def run() -> None:
        with pytest.raises(OrderRejectedError, match="insufficient funds"):
            await client.place_order("BTCUSDT", "buy", 100.0, "MARKET")

    import asyncio

    asyncio.run(run())


def test_live_client_missing_keys_raises() -> None:
    with pytest.raises(Exception):
        LiveExecutionClient(api_key="", api_secret="")


def test_factory_live_builds_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAY_BINANCE_LIVE_API_KEY", "lk")
    monkeypatch.setenv("CLAY_BINANCE_LIVE_API_SECRET", "ls")
    client = build_execution_client(mode="live")
    assert client.source == "binance_live"


def test_guard_cap_zero_passes(mock_ccxt, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_cls, mock_instance = mock_ccxt
    monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
    client = LiveExecutionClient(
        api_key="k", api_secret="s", max_order_notional_usdt=0.0
    )
    mock_instance.create_order.return_value = {
        "id": "1",
        "clientOrderId": "",
        "symbol": "BTCUSDT",
        "side": "buy",
        "amount": 1000.0,
        "price": 100000.0,
        "status": "FILLED",
        "timestamp": 0,
        "filled": 1000.0,
        "trades": [],
    }

    async def run() -> None:
        result = await client.place_order("BTCUSDT", "buy", 1000.0, "MARKET")
        assert result.exchange_order_id == "1"

    import asyncio

    asyncio.run(run())


def test_guard_over_cap_rejects_before_ccxt(
    mock_ccxt, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_cls, mock_instance = mock_ccxt
    monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
    client = LiveExecutionClient(
        api_key="k", api_secret="s", max_order_notional_usdt=50.0
    )

    async def run() -> None:
        with pytest.raises(OrderRejectedError, match="exceeds cap"):
            await client.place_order("BTCUSDT", "buy", 0.01, "MARKET", price=100000.0)
        mock_instance.create_order.assert_not_called()

    import asyncio

    asyncio.run(run())


def test_guard_market_order_missing_price_fails_closed(
    mock_ccxt, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_cls, mock_instance = mock_ccxt
    monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
    client = LiveExecutionClient(
        api_key="k", api_secret="s", max_order_notional_usdt=50.0
    )

    async def run() -> None:
        with pytest.raises(OrderRejectedError, match="price is unknown"):
            await client.place_order("BTCUSDT", "buy", 0.01, "MARKET", price=None)
        mock_instance.create_order.assert_not_called()

    import asyncio

    asyncio.run(run())
