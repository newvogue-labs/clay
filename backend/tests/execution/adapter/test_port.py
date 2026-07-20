"""Tests for ExchangeAdapter protocol — runtime_checkable + FakeAdapter."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from clay.execution.adapter.domain import (
    BalanceSnapshot,
    OrderAck,
    OrderRequest,
    OrderSnapshot,
)
from clay.execution.adapter.enums import (
    CancelResult,
    Environment,
    OrderSide,
    OrderState,
    OrderType,
    TimeInForce,
)
from clay.execution.adapter.normalization import quantize_order, validate_order
from clay.execution.adapter.port import ExchangeAdapter
from clay.execution.adapter.rules import MarketRules
from clay.execution.adapter.enums import PrecisionMode


# ---------------------------------------------------------------------------
# FakeAdapter — in-memory, satisfies ExchangeAdapter
# ---------------------------------------------------------------------------


class FakeAdapter:
    """Minimal in-memory adapter for protocol checks."""

    environment: Environment = Environment.PAPER
    _orders: dict[str, OrderRequest] = {}

    def validate_order(self, req: OrderRequest, rules: MarketRules) -> None:
        validate_order(req, rules)

    def quantize_order(self, req: OrderRequest, rules: MarketRules) -> OrderRequest:
        return quantize_order(req, rules)

    async def get_market_rules(self, symbol: str) -> MarketRules:
        return _default_rules()

    async def place_order(self, req: OrderRequest) -> OrderAck:
        self._orders[req.client_order_id] = req
        return OrderAck(
            client_order_id=req.client_order_id,
            venue_order_id=f"venue-{req.client_order_id}",
            symbol=req.symbol,
            side=req.side,
            order_type=req.order_type,
            state=OrderState.NEW,
            quantity=req.quantity,
            price=req.price,
            transact_time=1700000000000,
        )

    async def cancel_order(
        self, symbol: str, venue_order_id: str
    ) -> CancelResult:
        return CancelResult.CANCELED

    async def get_order(self, symbol: str, venue_order_id: str) -> OrderSnapshot:
        return OrderSnapshot(
            client_order_id="c-1",
            venue_order_id=venue_order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            state=OrderState.NEW,
            quantity=Decimal("0.01"),
            executed_qty=Decimal("0"),
            price=Decimal("50000"),
            transact_time=1700000000000,
        )

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderSnapshot]:
        return []

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]:
        return []

    async def get_balances(self) -> list[BalanceSnapshot]:
        return [
            BalanceSnapshot(
                asset="USDT",
                free=Decimal("10000"),
                locked=Decimal("0"),
                total=Decimal("10000"),
            )
        ]

    async def get_my_trades(
        self, symbol: str, *, since: datetime | None = None, from_id: str | None = None
    ) -> list:
        return []

    async def get_by_client_order_id(
        self, symbol: str, client_order_id: str
    ) -> OrderSnapshot | None:
        return None


# ---------------------------------------------------------------------------
# Protocol check
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_fake_satisfies_protocol(self) -> None:
        assert isinstance(FakeAdapter(), ExchangeAdapter)

    def test_incomplete_class_fails(self) -> None:
        class NoEnv:
            pass

        assert not isinstance(NoEnv(), ExchangeAdapter)

    def test_missing_async_method_fails(self) -> None:
        class Partial:
            environment = Environment.PAPER

            def validate_order(self, req: object, rules: object) -> None: ...
            def quantize_order(self, req: object, rules: object) -> object: ...

        assert not isinstance(Partial(), ExchangeAdapter)


# ---------------------------------------------------------------------------
# FakeAdapter integration
# ---------------------------------------------------------------------------


class TestFakeAdapterFlow:
    @pytest.fixture
    def adapter(self) -> FakeAdapter:
        return FakeAdapter()

    @pytest.fixture
    def rules(self) -> MarketRules:
        return _default_rules()

    @pytest.fixture
    def order_request(self) -> OrderRequest:
        return OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            time_in_force=TimeInForce.GTC,
            client_order_id="flow-001",
        )

    @pytest.mark.anyio
    async def test_quantize_then_validate_then_place(
        self, adapter: FakeAdapter, rules: MarketRules, order_request: OrderRequest
    ) -> None:
        quantized = adapter.quantize_order(order_request, rules)
        adapter.validate_order(quantized, rules)
        ack = await adapter.place_order(quantized)

        assert ack.client_order_id == "flow-001"
        assert ack.state == OrderState.NEW
        assert isinstance(ack.quantity, Decimal)
        assert ack.venue_order_id.startswith("venue-")

    @pytest.mark.anyio
    async def test_get_balances(self, adapter: FakeAdapter) -> None:
        balances = await adapter.get_balances()
        assert len(balances) == 1
        assert balances[0].asset == "USDT"
        assert isinstance(balances[0].free, Decimal)

    @pytest.mark.anyio
    async def test_cancel_order_noop(self, adapter: FakeAdapter) -> None:
        await adapter.cancel_order("BTCUSDT", "v-1")  # no raise

    @pytest.mark.anyio
    async def test_get_order(self, adapter: FakeAdapter) -> None:
        snap = await adapter.get_order("BTCUSDT", "v-1")
        assert snap.venue_order_id == "v-1"
        assert isinstance(snap.executed_qty, Decimal)

    @pytest.mark.anyio
    async def test_get_open_orders_empty(self, adapter: FakeAdapter) -> None:
        orders = await adapter.get_open_orders()
        assert orders == []


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _default_rules() -> MarketRules:
    return MarketRules(
        min_amount=Decimal("0.001"),
        max_amount=Decimal("1000"),
        min_price=Decimal("0.01"),
        max_price=Decimal("1000000"),
        min_notional=Decimal("10"),
        amount_step=Decimal("0.001"),
        price_tick=Decimal("0.01"),
        precision_mode=PrecisionMode.TICK_SIZE,
        supported_order_types=frozenset(
            {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT}
        ),
        supported_tif=frozenset({TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK}),
    )
