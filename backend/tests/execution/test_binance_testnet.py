"""Tests for Binance testnet execution client (mocked ccxt)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from clay.execution.binance_testnet import BinanceTestnetExecutionClient
from clay.execution.exceptions import ExecutionConfigError, PartialFillError


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
    mock_instance.set_sandbox_mode = MagicMock()
    mock_instance.urls = {"api": "https://testnet.binance.vision"}
    mock_cls.return_value = mock_instance
    return mock_cls, mock_instance


def test_client_order_id_passthrough(
    mock_ccxt, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_cls, mock_instance = mock_ccxt
    monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
    client = BinanceTestnetExecutionClient(api_key="k", api_secret="s")
    mock_instance.create_order.return_value = {
        "id": "123",
        "clientOrderId": "cid-1",
        "symbol": "BTCUSDT",
        "side": "buy",
        "amount": 0.01,
        "price": 30000.0,
        "status": "FILLED",
        "timestamp": 1_700_000_000_000,
        "filled": 0.01,
        "trades": [
            {
                "id": "t1",
                "amount": 0.01,
                "price": 30000.0,
                "commission": 0.00001,
                "commissionAsset": "BNB",
                "timestamp": 1_700_000_000_000,
            }
        ],
    }

    async def run() -> None:
        result = await client.place_order(
            "BTCUSDT", "buy", 0.01, "MARKET", client_order_id="cid-1"
        )
        assert result.client_order_id == "cid-1"
        assert result.exchange_order_id == "123"

    import asyncio

    asyncio.run(run())


def test_partial_fill_raises(mock_ccxt, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_cls, mock_instance = mock_ccxt
    monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
    client = BinanceTestnetExecutionClient(api_key="k", api_secret="s")
    mock_instance.create_order.return_value = {
        "id": "123",
        "clientOrderId": "cid",
        "symbol": "BTCUSDT",
        "side": "buy",
        "amount": 0.01,
        "price": 30000.0,
        "status": "PARTIALLY_FILLED",
        "timestamp": 1_700_000_000_000,
        "filled": 0.005,
        "trades": [],
    }

    async def run() -> None:
        with pytest.raises(PartialFillError, match="partial fill"):
            await client.place_order("BTCUSDT", "buy", 0.01, "MARKET")

    import asyncio

    asyncio.run(run())


def test_missing_keys_raises() -> None:
    with pytest.raises(ExecutionConfigError, match="required"):
        BinanceTestnetExecutionClient(api_key="", api_secret="")


def test_get_order_status_not_found(mock_ccxt, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    import ccxt.async_support as ccxt

    mock_cls, mock_instance = mock_ccxt
    monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
    client = BinanceTestnetExecutionClient(api_key="k", api_secret="s")
    mock_instance.fetch_order.side_effect = ccxt.OrderNotFound("missing")

    async def run() -> None:
        status = await client.get_order_status("BTCUSDT", "404")
        assert status.status == "not_found"
        assert status.exchange_order_id == "404"
        assert status.symbol == "BTCUSDT"
        assert status.executed_qty == 0.0

    asyncio.run(run())


def test_get_order_status_success(mock_ccxt, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    mock_cls, mock_instance = mock_ccxt
    monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
    client = BinanceTestnetExecutionClient(api_key="k", api_secret="s")
    mock_instance.fetch_order.return_value = {
        "id": "123",
        "clientOrderId": "cid-9",
        "symbol": "BTCUSDT",
        "side": "buy",
        "type": "LIMIT",
        "status": "FILLED",
        "amount": 0.02,
        "filled": 0.02,
        "price": 30000.0,
        "timestamp": 1_700_000_000_000,
    }

    async def run() -> None:
        status = await client.get_order_status("BTCUSDT", "123")
        assert status.exchange_order_id == "123"
        assert status.client_order_id == "cid-9"
        assert status.status == "FILLED"
        assert status.executed_qty == 0.02

    asyncio.run(run())
