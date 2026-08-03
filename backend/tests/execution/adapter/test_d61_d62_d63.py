"""Tests for D-61/D-62/D-63 — execution cluster fixes (offline, ccxt mocked).

- D-61: fill time comes from fetch_my_trades (venue truth), not create_order;
  fallback (log + keep) when trades are unavailable/empty — never raises.
- D-62: connector is closed on every path via the adapter's async context
  and explicit ``close()``.
- D-63: Binance get_open_orders requires symbol — fails fast, never sends a
  request the venue would reject.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from clay.execution.adapter.binance import BinanceExecutionAdapter
from clay.execution.adapter.ccxt_base import CcxtExchangeAdapter
from clay.execution.adapter.ccxt_client import CcxtSpotClient
from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import (
    Environment,
    OrderSide,
    OrderType,
    TimeInForce,
)

# ---------------------------------------------------------------------------
# D-61: fill time from fetch_my_trades
# ---------------------------------------------------------------------------


class _D61StubAdapter(CcxtExchangeAdapter):
    """Concrete stub exposing place_order's fill-time enrichment."""

    supported_order_types = frozenset({OrderType.LIMIT})
    supported_tif = frozenset({TimeInForce.GTC})

    def _build_client(self, api_key: str, api_secret: str) -> CcxtSpotClient:
        return MagicMock()

    def _is_duplicate_cid(self, exc: Exception) -> bool:
        return False

    def _build_order_params(self, req: OrderRequest) -> dict[str, Any]:
        return {}

    async def get_market_rules(self, symbol: str) -> Any:
        raise NotImplementedError


def _make_request(
    *, symbol: str = "BTC/USDT", client_order_id: str = "cid-d61"
) -> OrderRequest:
    return OrderRequest(
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.001"),
        price=Decimal("40000"),
        time_in_force=TimeInForce.GTC,
        client_order_id=client_order_id,
    )


def _filled_create_response() -> dict[str, Any]:
    """create_order response: FILLED with a create-order timestamp."""
    return {
        "id": "venue-9",
        "clientOrderId": "cid-d61",
        "symbol": "BTC/USDT",
        "side": "buy",
        "type": "limit",
        "status": "closed",
        "amount": "0.001",
        "filled": "0.001",
        "price": "40000",
        "timestamp": 1700000000000,
        "trades": [],
    }


class TestD61FillTimeFromMyTrades:
    @pytest.mark.anyio
    async def test_fill_time_taken_from_last_my_trade(self) -> None:
        """D-61: transact_time = max fill timestamp, not create_order time."""
        adapter = _D61StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")
        adapter._client.create_order = AsyncMock(return_value=_filled_create_response())
        adapter._client.fetch_my_trades = AsyncMock(
            return_value=[
                {
                    "id": "t1",
                    "order": "venue-9",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "amount": "0.0005",
                    "price": "40000",
                    "timestamp": 1700000100000,
                },
                {
                    "id": "t2",
                    "order": "venue-9",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "amount": "0.0005",
                    "price": "40001",
                    "timestamp": 1700000200000,
                },
            ]
        )

        ack = await adapter.place_order(_make_request())

        # create_order says 1700000000000; last fill is 1700000200000.
        assert ack.transact_time == 1700000200000

    @pytest.mark.anyio
    async def test_fallback_when_trades_unavailable(self) -> None:
        """D-61: fetch_my_trades raising → keep create-order time, no crash."""
        adapter = _D61StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")
        adapter._client.create_order = AsyncMock(return_value=_filled_create_response())
        adapter._client.fetch_my_trades = AsyncMock(
            side_effect=RuntimeError("venue hiccup")
        )

        ack = await adapter.place_order(_make_request())

        assert ack.transact_time == 1700000000000

    @pytest.mark.anyio
    async def test_fallback_when_trades_empty(self) -> None:
        """D-61: fetch_my_trades returns [] → keep create-order time."""
        adapter = _D61StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")
        adapter._client.create_order = AsyncMock(return_value=_filled_create_response())
        adapter._client.fetch_my_trades = AsyncMock(return_value=[])

        ack = await adapter.place_order(_make_request())

        assert ack.transact_time == 1700000000000

    @pytest.mark.anyio
    async def test_fallback_when_no_matching_order(self) -> None:
        """D-61: trades for another order → no match → keep create-order time."""
        adapter = _D61StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")
        adapter._client.create_order = AsyncMock(return_value=_filled_create_response())
        adapter._client.fetch_my_trades = AsyncMock(
            return_value=[
                {
                    "id": "t9",
                    "order": "other-order",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "amount": "0.5",
                    "price": "40000",
                    "timestamp": 1700000300000,
                }
            ]
        )

        ack = await adapter.place_order(_make_request())

        assert ack.transact_time == 1700000000000


# ---------------------------------------------------------------------------
# D-62: connector closed on every path
# ---------------------------------------------------------------------------


class TestD62ConnectorClosed:
    @pytest.mark.anyio
    async def test_close_called_on_success_path(self) -> None:
        adapter = _D61StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")
        adapter._client.close = AsyncMock()
        await adapter.close()
        adapter._client.close.assert_awaited_once()

    @pytest.mark.anyio
    async def test_async_context_closes_on_success(self) -> None:
        adapter = _D61StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")
        adapter._client.close = AsyncMock()
        async with adapter:
            pass
        adapter._client.close.assert_awaited_once()

    @pytest.mark.anyio
    async def test_async_context_closes_on_exception(self) -> None:
        """D-62: close() still runs when the body raises (finally semantics)."""
        adapter = _D61StubAdapter(Environment.PRODUCTION, api_key="k", api_secret="s")
        adapter._client.close = AsyncMock()
        with pytest.raises(RuntimeError, match="boom"):
            async with adapter:
                raise RuntimeError("boom")
        adapter._client.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# D-63: Binance open-orders require symbol
# ---------------------------------------------------------------------------


def _binance_with(client: CcxtSpotClient) -> BinanceExecutionAdapter:
    return BinanceExecutionAdapter(Environment.PRODUCTION, client=client)


class TestD63BinanceOpenOrdersSymbolRequired:
    @pytest.mark.anyio
    async def test_symbol_forwarded(self) -> None:
        """D-63: known symbol is always forwarded to fetch_open_orders."""
        client = MagicMock()
        client.set_sandbox_mode = MagicMock()
        client.fetch_open_orders = AsyncMock(return_value=[])
        adapter = _binance_with(client)

        await adapter.get_open_orders("BTC/USDT")

        client.fetch_open_orders.assert_awaited_once_with(symbol="BTC/USDT")

    @pytest.mark.anyio
    async def test_no_symbol_fails_fast(self) -> None:
        """D-63: symbol-less query fails fast; venue never hit."""
        client = MagicMock()
        client.set_sandbox_mode = MagicMock()
        client.fetch_open_orders = AsyncMock(return_value=[])
        adapter = _binance_with(client)

        with pytest.raises(Exception, match="requires symbol"):
            await adapter.get_open_orders()

        client.fetch_open_orders.assert_not_awaited()
