"""Shared ccxt mock fixtures for execution tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_ccxt():
    """Fake ccxt.binance class + instance with all async methods mocked.

    Usage in test::

        def test_something(mock_ccxt, monkeypatch):
            mock_cls, mock_instance = mock_ccxt
            monkeypatch.setattr("ccxt.async_support.binance", mock_cls, raising=False)
            client = BinanceTestnetExecutionClient(api_key="k", api_secret="s")
            mock_instance.create_order.return_value = {...}
            ...
    """
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
