"""Tests for ResilientExecutionAdapter (S-ADAPT-3).

Covers:
  - D1: isinstance(ResilientExecutionAdapter(fake), ExchangeAdapter)
  - D2: place_order — happy passthrough, ambiguous→reconcile-hit (no re-place),
        ambiguous→absent→re-place same cid→success, ambiguous unresolved→raise,
        terminal→immediate propagation
  - D3: read-retry — Transient retry success, Transient exhaust
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from clay.execution.adapter.domain import (
    BalanceSnapshot,
    OrderAck,
    OrderRequest,
    OrderSnapshot,
)
from clay.execution.adapter.enums import (
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
    OperationNotAllowedError,
    OrderRejectedError,
    TransientAdapterError,
)
from clay.execution.adapter.port import ExchangeAdapter
from clay.execution.adapter.rules import MarketRules
from clay.execution.resilience import RetryPolicy, ResilientExecutionAdapter


# ---------------------------------------------------------------------------
# FakeInnerAdapter — configurable, in-memory
# ---------------------------------------------------------------------------


class FakeInnerAdapter:
    """Configurable fake adapter for resilience tests.

    Each method's behavior can be set via ``set_*`` helpers:
    - default: returns a canned success response
    - side_effect: raises the given exception on next call
    - return_value: returns the given value on next call
    """

    def __init__(self) -> None:
        self.environment: Environment = Environment.PAPER
        self._place_calls: list[OrderRequest] = []
        self._reconcile_calls: list[tuple[str, datetime]] = []
        self._get_market_rules_calls: int = 0
        self._get_order_calls: int = 0
        self._get_open_orders_calls: int = 0
        self._get_balances_calls: int = 0
        self._cancel_order_calls: int = 0

        # Configurable side effects (deque-like: pop on each call)
        self._place_effects: list[Any] = []
        self._reconcile_effects: list[Any] = []
        self._get_market_rules_effects: list[Any] = []
        self._get_order_effects: list[Any] = []
        self._get_open_orders_effects: list[Any] = []
        self._get_balances_effects: list[Any] = []

    # -- helpers to configure behavior --

    def set_place_effect(self, effect: Any) -> None:
        """Set the next place_order to raise/return *effect*."""
        self._place_effects.append(effect)

    def set_reconcile_effect(self, effect: Any) -> None:
        """Set the next reconcile_orders to raise/return *effect*."""
        self._reconcile_effects.append(effect)

    def set_get_market_rules_effect(self, effect: Any) -> None:
        self._get_market_rules_effects.append(effect)

    def set_get_order_effect(self, effect: Any) -> None:
        self._get_order_effects.append(effect)

    def set_get_open_orders_effect(self, effect: Any) -> None:
        self._get_open_orders_effects.append(effect)

    def set_get_balances_effect(self, effect: Any) -> None:
        self._get_balances_effects.append(effect)

    # -- protocol methods --

    def validate_order(self, req: OrderRequest, rules: MarketRules) -> None:
        pass

    def quantize_order(self, req: OrderRequest, rules: MarketRules) -> OrderRequest:
        return req

    async def get_market_rules(self, symbol: str) -> MarketRules:
        self._get_market_rules_calls += 1
        if self._get_market_rules_effects:
            eff = self._get_market_rules_effects.pop(0)
            if isinstance(eff, BaseException):
                raise eff
            return eff
        return _default_rules()

    async def place_order(self, req: OrderRequest) -> OrderAck:
        self._place_calls.append(req)
        if self._place_effects:
            eff = self._place_effects.pop(0)
            if isinstance(eff, BaseException):
                raise eff
            return eff
        return _make_ack(req)

    async def cancel_order(self, symbol: str, venue_order_id: str) -> None:
        self._cancel_order_calls += 1

    async def get_order(self, symbol: str, venue_order_id: str) -> OrderSnapshot:
        self._get_order_calls += 1
        if self._get_order_effects:
            eff = self._get_order_effects.pop(0)
            if isinstance(eff, BaseException):
                raise eff
            return eff
        return _make_snapshot(venue_order_id, symbol)

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderSnapshot]:
        self._get_open_orders_calls += 1
        if self._get_open_orders_effects:
            eff = self._get_open_orders_effects.pop(0)
            if isinstance(eff, BaseException):
                raise eff
            return eff
        return []

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]:
        self._reconcile_calls.append((symbol, since))
        if self._reconcile_effects:
            eff = self._reconcile_effects.pop(0)
            if isinstance(eff, BaseException):
                raise eff
            return eff
        return []

    async def get_balances(self) -> list[BalanceSnapshot]:
        self._get_balances_calls += 1
        if self._get_balances_effects:
            eff = self._get_balances_effects.pop(0)
            if isinstance(eff, BaseException):
                raise eff
            return eff
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CID = "test-cid-001"
SYMBOL = "BTCUSDT"


def _make_req(cid: str = CID) -> OrderRequest:
    return OrderRequest(
        symbol=SYMBOL,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("50000"),
        time_in_force=TimeInForce.GTC,
        client_order_id=cid,
    )


def _make_ack(req: OrderRequest) -> OrderAck:
    return OrderAck(
        client_order_id=req.client_order_id,
        venue_order_id="venue-001",
        symbol=req.symbol,
        side=req.side,
        order_type=req.order_type,
        state=OrderState.NEW,
        quantity=req.quantity,
        price=req.price,
        transact_time=1700000000000,
    )


def _make_snapshot(
    venue_order_id: str = "venue-001",
    symbol: str = SYMBOL,
    cid: str = CID,
) -> OrderSnapshot:
    return OrderSnapshot(
        client_order_id=cid,
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


def _fast_policy() -> RetryPolicy:
    """Fast policy for tests — minimal delays."""
    return RetryPolicy(
        max_place_attempts=2,
        max_read_attempts=3,
        base_delay_s=Decimal("0.001"),
        max_delay_s=Decimal("0.01"),
        reconcile_skew_s=5,
    )


# ---------------------------------------------------------------------------
# D1: Protocol runtime_checkable
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_resilient_satisfies_exchange_adapter(self) -> None:
        inner = FakeInnerAdapter()
        resilient = ResilientExecutionAdapter(inner)  # type: ignore[arg-type]
        assert isinstance(resilient, ExchangeAdapter)

    def test_environment_delegates_to_inner(self) -> None:
        inner = FakeInnerAdapter()
        inner.environment = Environment.TESTNET
        resilient = ResilientExecutionAdapter(inner)  # type: ignore[arg-type]
        assert resilient.environment == Environment.TESTNET


# ---------------------------------------------------------------------------
# D2: place_order — reconcile-before-retry
# ---------------------------------------------------------------------------


class TestPlaceOrderHappyPath:
    @pytest.mark.anyio
    async def test_passthrough_on_success(self) -> None:
        inner = FakeInnerAdapter()
        resilient = ResilientExecutionAdapter(inner, _fast_policy())  # type: ignore[arg-type]
        req = _make_req()

        ack = await resilient.place_order(req)

        assert ack.client_order_id == CID
        assert ack.venue_order_id == "venue-001"
        assert len(inner._place_calls) == 1
        assert inner._reconcile_calls == []  # no reconcile needed


class TestPlaceOrderAmbiguousReconcileHit:
    @pytest.mark.anyio
    async def test_ambiguous_then_reconcile_hit_no_re_place(self) -> None:
        """Ambiguous → reconcile finds matching cid → return ack, NO re-place."""
        inner = FakeInnerAdapter()
        # First place: ambiguous
        inner.set_place_effect(AmbiguousExecutionError("timeout"))
        # Reconcile returns matching snapshot
        inner.set_reconcile_effect([_make_snapshot()])
        resilient = ResilientExecutionAdapter(inner, _fast_policy())  # type: ignore[arg-type]
        req = _make_req()

        ack = await resilient.place_order(req)

        assert ack.client_order_id == CID
        assert ack.venue_order_id == "venue-001"
        # Only 1 place call (the initial), NO re-place
        assert len(inner._place_calls) == 1
        # 1 reconcile call
        assert len(inner._reconcile_calls) == 1


class TestPlaceOrderAmbiguousReconcileMiss:
    @pytest.mark.anyio
    async def test_ambiguous_then_absent_then_re_place_success(self) -> None:
        """Ambiguous → reconcile empty → re-place same cid → success."""
        inner = FakeInnerAdapter()
        # First place: ambiguous
        inner.set_place_effect(AmbiguousExecutionError("timeout"))
        # Reconcile: empty (order not found)
        inner.set_reconcile_effect([])
        # Re-place: success
        inner.set_place_effect(_make_ack(_make_req()))
        resilient = ResilientExecutionAdapter(inner, _fast_policy())  # type: ignore[arg-type]
        req = _make_req()

        ack = await resilient.place_order(req)

        assert ack.client_order_id == CID
        assert len(inner._place_calls) == 2  # initial + re-place
        assert inner._place_calls[0].client_order_id == CID
        assert inner._place_calls[1].client_order_id == CID  # same cid!
        assert len(inner._reconcile_calls) == 1


class TestPlaceOrderAmbiguousUnresolved:
    @pytest.mark.anyio
    async def test_ambiguous_unresolved_raises_after_attempts(self) -> None:
        """All attempts ambiguous + no reconcile hit → raise.

        With max_place_attempts=2: 1 initial place + 1 re-place in loop = 2 total.
        """
        inner = FakeInnerAdapter()
        # Initial place: ambiguous
        inner.set_place_effect(AmbiguousExecutionError("timeout"))
        # Loop iter 0 (only iteration): reconcile empty, re-place ambiguous
        inner.set_reconcile_effect([])
        inner.set_place_effect(AmbiguousExecutionError("timeout"))
        # Final reconcile after loop: empty
        inner.set_reconcile_effect([])
        resilient = ResilientExecutionAdapter(inner, _fast_policy())  # type: ignore[arg-type]
        req = _make_req()

        with pytest.raises(AmbiguousExecutionError, match="unresolved"):
            await resilient.place_order(req)

        # CID identical in all place attempts (2 total)
        assert len(inner._place_calls) == 2
        for call in inner._place_calls:
            assert call.client_order_id == CID


class TestPlaceOrderTerminalPropagation:
    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "error_cls",
        [
            OrderRejectedError,
            InsufficientFundsError,
            InvalidOrderError,
            ConfigError,
            OperationNotAllowedError,
        ],
    )
    async def test_terminal_error_propagates_immediately(self, error_cls: type) -> None:
        """Terminal errors bypass reconcile and propagate."""
        inner = FakeInnerAdapter()
        inner.set_place_effect(error_cls("terminal failure"))
        resilient = ResilientExecutionAdapter(inner, _fast_policy())  # type: ignore[arg-type]
        req = _make_req()

        with pytest.raises(error_cls, match="terminal failure"):
            await resilient.place_order(req)

        # No reconcile attempted
        assert len(inner._place_calls) == 1
        assert inner._reconcile_calls == []

    @pytest.mark.anyio
    async def test_duplicate_cid_on_re_place_propagates_immediately(self) -> None:
        """Re-place with same cid hits DuplicateOrderId (InvalidOrderError).

        Binance rejects duplicate newClientOrderId → InvalidOrderError (terminal).
        The resilience wrapper propagates it immediately, no second reconcile.
        """
        inner = FakeInnerAdapter()
        # Initial place: ambiguous
        inner.set_place_effect(AmbiguousExecutionError("timeout"))
        # Reconcile: empty (eventual consistency miss)
        inner.set_reconcile_effect([])
        # Re-place: duplicate cid → InvalidOrderError (terminal)
        inner.set_place_effect(InvalidOrderError("duplicate clientOrderId"))
        resilient = ResilientExecutionAdapter(inner, _fast_policy())  # type: ignore[arg-type]
        req = _make_req()

        with pytest.raises(InvalidOrderError, match="duplicate clientOrderId"):
            await resilient.place_order(req)

        # 2 place calls (initial + re-place), 1 reconcile — no more
        assert len(inner._place_calls) == 2
        assert inner._place_calls[0].client_order_id == CID
        assert inner._place_calls[1].client_order_id == CID
        assert len(inner._reconcile_calls) == 1


# ---------------------------------------------------------------------------
# D3: read-retry — TransientAdapterError
# ---------------------------------------------------------------------------


class TestReadRetry:
    @pytest.mark.anyio
    async def test_transient_then_success(self) -> None:
        """Transient × 1 + success → returns result."""
        inner = FakeInnerAdapter()
        inner.set_get_balances_effect(TransientAdapterError("network"))
        inner.set_get_balances_effect(
            [
                BalanceSnapshot(
                    asset="USDT",
                    free=Decimal("100"),
                    locked=Decimal("0"),
                    total=Decimal("100"),
                )
            ]
        )
        resilient = ResilientExecutionAdapter(inner, _fast_policy())  # type: ignore[arg-type]

        result = await resilient.get_balances()

        assert len(result) == 1
        assert result[0].asset == "USDT"
        assert inner._get_balances_calls == 2

    @pytest.mark.anyio
    async def test_transient_exhaust_propagates(self) -> None:
        """Transient × max_read_attempts → raise last TransientAdapterError."""
        inner = FakeInnerAdapter()
        inner.set_get_balances_effect(TransientAdapterError("net-1"))
        inner.set_get_balances_effect(TransientAdapterError("net-2"))
        inner.set_get_balances_effect(TransientAdapterError("net-3"))
        resilient = ResilientExecutionAdapter(inner, _fast_policy())  # type: ignore[arg-type]

        with pytest.raises(TransientAdapterError, match="net-3"):
            await resilient.get_balances()

        assert inner._get_balances_calls == 3

    @pytest.mark.anyio
    async def test_terminal_during_read_no_retry(self) -> None:
        """Terminal error during read → immediate propagation, no retry."""
        inner = FakeInnerAdapter()
        inner.set_get_balances_effect(ConfigError("bad config"))
        resilient = ResilientExecutionAdapter(inner, _fast_policy())  # type: ignore[arg-type]

        with pytest.raises(ConfigError, match="bad config"):
            await resilient.get_balances()

        assert inner._get_balances_calls == 1

    @pytest.mark.anyio
    async def test_passthrough_sync_methods(self) -> None:
        """validate_order and quantize_order passthrough to inner."""
        inner = FakeInnerAdapter()
        resilient = ResilientExecutionAdapter(inner, _fast_policy())  # type: ignore[arg-type]
        req = _make_req()
        rules = _default_rules()

        resilient.validate_order(req, rules)
        result = resilient.quantize_order(req, rules)

        assert result == req
