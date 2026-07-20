"""Tests for D-12d D9: get-by-client-order-id venue-hook."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from clay.execution.adapter.domain import OrderSnapshot
from clay.execution.adapter.enums import (
    OrderSide,
    OrderState,
    OrderType,
)
from clay.execution.adapter.ccxt_base import CcxtExchangeAdapter


def _make_snapshot(
    *,
    client_order_id: str = "test-cid-001",
    venue_order_id: str = "venue-001",
    state: OrderState = OrderState.NEW,
) -> OrderSnapshot:
    return OrderSnapshot(
        client_order_id=client_order_id,
        venue_order_id=venue_order_id,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        state=state,
        quantity=Decimal("0.001"),
        executed_qty=Decimal("0"),
        price=Decimal("50000"),
        transact_time=int(datetime.now(UTC).timestamp() * 1000),
        fills=(),
    )


class _StubCcxtAdapter(CcxtExchangeAdapter):
    """Minimal stub for testing get_by_client_order_id."""

    def __init__(self) -> None:
        self.environment = None
        self._open_orders: list[OrderSnapshot] = []
        self._reconcile_orders: list[OrderSnapshot] = []

    async def get_market_rules(self, symbol: str):
        raise NotImplementedError

    def _build_client(self, api_key: str, api_secret: str):
        raise NotImplementedError

    def _is_duplicate_cid(self, exc: Exception) -> bool:
        return False

    def _build_order_params(self, req):
        return {}

    async def get_open_orders(self, symbol=None):
        return self._open_orders

    async def reconcile_orders(self, symbol, since):
        return self._reconcile_orders


class TestGetByClientOrderId:
    @pytest.mark.asyncio
    async def test_found_in_open_orders(self) -> None:
        """Order found in open_orders → return snapshot."""
        adapter = _StubCcxtAdapter()
        adapter._open_orders = [_make_snapshot(client_order_id="target-cid")]

        result = await adapter.get_by_client_order_id("BTCUSDT", "target-cid")

        assert result is not None
        assert result.client_order_id == "target-cid"

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self) -> None:
        """Order not found → return None."""
        adapter = _StubCcxtAdapter()
        adapter._open_orders = []

        result = await adapter.get_by_client_order_id("BTCUSDT", "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_found_in_reconcile_fallback(self) -> None:
        """Order found in reconcile history fallback → return snapshot."""
        adapter = _StubCcxtAdapter()
        adapter._open_orders = []
        adapter._reconcile_orders = [_make_snapshot(client_order_id="target-cid")]

        result = await adapter.get_by_client_order_id("BTCUSDT", "target-cid")

        assert result is not None
        assert result.client_order_id == "target-cid"

    @pytest.mark.asyncio
    async def test_not_found_after_both_paths(self) -> None:
        """Order not found in either path → return None."""
        adapter = _StubCcxtAdapter()
        adapter._open_orders = []
        adapter._reconcile_orders = []

        result = await adapter.get_by_client_order_id("BTCUSDT", "nonexistent")

        assert result is None
