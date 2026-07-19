"""Tests for ResilientExecutionAdapter (S-ADAPT-3 + S-ADAPT-4).

Covers:
  - Protocol: isinstance(ResilientExecutionAdapter(fake), ExchangeAdapter)
  - place_order: happy passthrough, ambiguous→reconcile-hit, ambiguous→absent→re-place,
    ambiguous unresolved→raise, terminal→immediate propagation
  - read-retry: Transient retry success, Transient exhaust, terminal propagation
  - CB: opens after threshold, OPEN→fast-fail, HALF_OPEN probe success/fail,
    taxonomy (terminal/ambiguous don't trip), place/cancel at OPEN, route 503
"""

from __future__ import annotations

import asyncio
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
    CircuitOpenError,
    ConfigError,
    InsufficientFundsError,
    InvalidOrderError,
    OperationNotAllowedError,
    OrderNotFoundError,
    OrderRejectedError,
    TransientAdapterError,
)
from clay.execution.adapter.port import ExchangeAdapter
from clay.execution.adapter.rules import MarketRules
from clay.execution.resilience import (
    CircuitBreakerPolicy,
    RetryPolicy,
    ResilientExecutionAdapter,
)


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
        self._cancel_order_effects: list[Any] = []

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

    def set_cancel_order_effect(self, effect: Any) -> None:
        self._cancel_order_effects.append(effect)

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
        if self._cancel_order_effects:
            eff = self._cancel_order_effects.pop(0)
            if isinstance(eff, BaseException):
                raise eff

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


# ---------------------------------------------------------------------------
# OrderNotFoundError propagation — no retry, no CB trip
# ---------------------------------------------------------------------------


class TestOrderNotFoundErrorPropagation:
    @pytest.mark.anyio
    async def test_order_not_found_propagates_without_retry(self) -> None:
        """OrderNotFoundError from inner → immediate propagation, no retry."""
        inner = FakeInnerAdapter()
        inner.set_get_order_effect(
            OrderNotFoundError("not found", symbol="BTCUSDT", venue_order_id="v-1")
        )
        resilient = ResilientExecutionAdapter(inner, _fast_policy())  # type: ignore[arg-type]

        with pytest.raises(OrderNotFoundError, match="not found"):
            await resilient.get_order("BTCUSDT", "v-1")

        assert inner._get_order_calls == 1

    @pytest.mark.anyio
    async def test_order_not_found_does_not_trip_cb(self) -> None:
        """OrderNotFoundError does NOT trip the circuit breaker."""
        from clay.execution.resilience import _CBState

        inner = FakeInnerAdapter()
        inner.set_get_order_effect(
            OrderNotFoundError("not found", symbol="BTCUSDT", venue_order_id="v-1")
        )
        resilient = ResilientExecutionAdapter(
            inner, _fast_policy(), cb_policy=_cb_policy(threshold=1, reset_s="999")
        )  # type: ignore[arg-type]

        with pytest.raises(OrderNotFoundError):
            await resilient.get_order("BTCUSDT", "v-1")

        assert resilient._cb.state == _CBState.CLOSED


# ---------------------------------------------------------------------------
# S-ADAPT-4: CircuitBreaker tests
# ---------------------------------------------------------------------------


def _cb_policy(threshold: int = 5, reset_s: str = "30", probes: int = 1):
    return CircuitBreakerPolicy(
        failure_threshold=threshold,
        reset_timeout_s=Decimal(reset_s),
        half_open_max_probes=probes,
    )


class TestCircuitBreakerOpensAfterThreshold:
    @pytest.mark.anyio
    async def test_cb_opens_after_failure_threshold(self) -> None:
        """Transient × threshold → CB opens."""
        from clay.execution.resilience import CircuitBreaker, _CBState

        cb = CircuitBreaker(_cb_policy(threshold=3))

        async def _fail():
            raise TransientAdapterError("net")

        for _ in range(3):
            with pytest.raises(TransientAdapterError):
                await cb.call(_fail)

        assert cb.state == _CBState.OPEN

    @pytest.mark.anyio
    async def test_cb_resets_on_success(self) -> None:
        """Success resets failure counter."""
        from clay.execution.resilience import CircuitBreaker, _CBState

        cb = CircuitBreaker(_cb_policy(threshold=3))

        async def _fail():
            raise TransientAdapterError("net")

        async def _ok():
            return "ok"

        with pytest.raises(TransientAdapterError):
            await cb.call(_fail)
        with pytest.raises(TransientAdapterError):
            await cb.call(_fail)
        # Success resets
        assert await cb.call(_ok) == "ok"
        assert cb.state == _CBState.CLOSED

        # 2 more failures (below threshold)
        with pytest.raises(TransientAdapterError):
            await cb.call(_fail)
        with pytest.raises(TransientAdapterError):
            await cb.call(_fail)
        # Still CLOSED (only 2 consecutive)
        assert cb.state == _CBState.CLOSED


class TestCircuitBreakerOpenFastFail:
    @pytest.mark.anyio
    async def test_open_raises_circuit_open_without_calling_inner(self) -> None:
        """CB OPEN → CircuitOpenError, inner NOT called."""
        from clay.execution.resilience import CircuitBreaker, _CBState

        cb = CircuitBreaker(_cb_policy(threshold=1, reset_s="999"))
        call_count = 0

        async def _fail():
            nonlocal call_count
            call_count += 1
            raise TransientAdapterError("net")

        with pytest.raises(TransientAdapterError):
            await cb.call(_fail)
        assert cb.state == _CBState.OPEN

        async def _inner_call():
            nonlocal call_count
            call_count += 1
            return "should not reach"

        with pytest.raises(CircuitOpenError):
            await cb.call(_inner_call)

        # Only 1 call (the initial failure), inner NOT called when OPEN
        assert call_count == 1


class TestCircuitBreakerHalfOpen:
    @pytest.mark.anyio
    async def test_half_open_probe_success_closes(self) -> None:
        """After reset timeout: HALF_OPEN → probe success → CLOSED."""
        import time

        from clay.execution.resilience import CircuitBreaker, _CBState

        cb = CircuitBreaker(_cb_policy(threshold=1, reset_s="0.01"))

        async def _fail():
            raise TransientAdapterError("net")

        with pytest.raises(TransientAdapterError):
            await cb.call(_fail)
        assert cb.state == _CBState.OPEN

        # Wait for reset timeout
        time.sleep(0.02)

        async def _ok():
            return "recovered"

        result = await cb.call(_ok)
        assert result == "recovered"
        assert cb.state == _CBState.CLOSED

    @pytest.mark.anyio
    async def test_half_open_probe_fail_reopens(self) -> None:
        """After reset timeout: HALF_OPEN → probe fail → OPEN."""
        import time

        from clay.execution.resilience import CircuitBreaker, _CBState

        cb = CircuitBreaker(_cb_policy(threshold=1, reset_s="0.01"))

        async def _fail():
            raise TransientAdapterError("net")

        with pytest.raises(TransientAdapterError):
            await cb.call(_fail)
        assert cb.state == _CBState.OPEN

        time.sleep(0.02)

        with pytest.raises(TransientAdapterError):
            await cb.call(_fail)
        assert cb.state == _CBState.OPEN

    @pytest.mark.anyio
    async def test_half_open_enforces_max_probes(self) -> None:
        """HALF_OPEN with max_probes=1: 2nd concurrent probe → CircuitOpenError."""
        import time

        from clay.execution.resilience import CircuitBreaker, _CBState

        cb = CircuitBreaker(_cb_policy(threshold=1, reset_s="0.01", probes=1))

        async def _fail():
            raise TransientAdapterError("net")

        with pytest.raises(TransientAdapterError):
            await cb.call(_fail)
        assert cb.state == _CBState.OPEN

        time.sleep(0.02)

        # First call transitions OPEN → HALF_OPEN (probes=1, allowed)
        async def _slow_ok():
            await asyncio.sleep(0.05)  # simulate slow probe
            return "probe-1"

        # Start first probe (will be in flight)
        task = asyncio.create_task(cb.call(_slow_ok))
        await asyncio.sleep(0.005)  # let it start

        # Second call while first probe in flight → rejected
        with pytest.raises(CircuitOpenError, match="half-open probe limit"):
            await cb.call(_slow_ok)

        # Wait for first probe to complete
        result = await task
        assert result == "probe-1"
        assert cb.state == _CBState.CLOSED  # success → CLOSED


class TestCircuitBreakerTaxonomy:
    @pytest.mark.anyio
    async def test_terminal_error_does_not_trip_cb(self) -> None:
        """Terminal errors pass through without affecting CB state."""
        from clay.execution.resilience import CircuitBreaker, _CBState

        cb = CircuitBreaker(_cb_policy(threshold=3))

        async def _fail_terminal():
            raise OrderRejectedError("rejected")

        for _ in range(5):
            with pytest.raises(OrderRejectedError):
                await cb.call(_fail_terminal)

        # CB still CLOSED — terminal doesn't trip
        assert cb.state == _CBState.CLOSED

    @pytest.mark.anyio
    async def test_ambiguous_error_does_not_trip_cb(self) -> None:
        """AmbiguousExecutionError passes through without affecting CB state."""
        from clay.execution.resilience import CircuitBreaker, _CBState

        cb = CircuitBreaker(_cb_policy(threshold=3))

        async def _fail_ambiguous():
            raise AmbiguousExecutionError("timeout")

        for _ in range(5):
            with pytest.raises(AmbiguousExecutionError):
                await cb.call(_fail_ambiguous)

        assert cb.state == _CBState.CLOSED

    @pytest.mark.anyio
    async def test_circuit_open_error_not_self_tripped(self) -> None:
        """CircuitOpenError (from CB itself) never counts as inner failure."""
        from clay.execution.resilience import CircuitBreaker, _CBState

        cb = CircuitBreaker(_cb_policy(threshold=1, reset_s="999"))

        async def _fail():
            raise TransientAdapterError("net")

        with pytest.raises(TransientAdapterError):
            await cb.call(_fail)
        assert cb.state == _CBState.OPEN

        # CircuitOpenError from CB — should NOT affect state further
        with pytest.raises(CircuitOpenError):
            await cb.call(lambda: _fail())  # noqa: B023

        assert cb.state == _CBState.OPEN  # unchanged


class TestResilientAdapterCBIntegration:
    @pytest.mark.anyio
    async def test_place_open_circuit_no_inner_calls(self) -> None:
        """CB OPEN + place_order → CircuitOpenError, zero inner place calls."""
        inner = FakeInnerAdapter()
        # Trip CB with threshold=1
        inner.set_place_effect(TransientAdapterError("net"))
        resilient = ResilientExecutionAdapter(
            inner, _fast_policy(), cb_policy=_cb_policy(threshold=1, reset_s="999")
        )  # type: ignore[arg-type]
        req = _make_req()

        # First call: transient → trips CB
        with pytest.raises(TransientAdapterError):
            await resilient.place_order(req)

        # Second call: CB OPEN → CircuitOpenError, no inner call
        with pytest.raises(CircuitOpenError):
            await resilient.place_order(req)

        # Only 1 inner place call total (the initial transient)
        assert len(inner._place_calls) == 1

    @pytest.mark.anyio
    async def test_cancel_open_circuit_no_inner_calls(self) -> None:
        """CB OPEN + cancel_order → CircuitOpenError, zero inner cancel calls."""
        inner = FakeInnerAdapter()
        # 3 transient failures to exhaust _retry_transient (max_read_attempts=3)
        inner.set_get_balances_effect(TransientAdapterError("net-1"))
        inner.set_get_balances_effect(TransientAdapterError("net-2"))
        inner.set_get_balances_effect(TransientAdapterError("net-3"))
        resilient = ResilientExecutionAdapter(
            inner, _fast_policy(), cb_policy=_cb_policy(threshold=1, reset_s="999")
        )  # type: ignore[arg-type]

        # Trip CB via get_balances (exhausted retry → 1 CB failure → OPEN)
        with pytest.raises(TransientAdapterError, match="net-3"):
            await resilient.get_balances()

        # cancel_order → CB OPEN → CircuitOpenError
        with pytest.raises(CircuitOpenError):
            await resilient.cancel_order("BTCUSDT", "v-1")

        assert inner._cancel_order_calls == 0

    @pytest.mark.anyio
    async def test_read_retry_composition_with_cb(self) -> None:
        """Read op: CB counts 1 failure per exhausted retry operation."""
        inner = FakeInnerAdapter()
        # 3 transient failures (exhausts _retry_transient with max_read_attempts=3)
        inner.set_get_balances_effect(TransientAdapterError("net-1"))
        inner.set_get_balances_effect(TransientAdapterError("net-2"))
        inner.set_get_balances_effect(TransientAdapterError("net-3"))
        resilient = ResilientExecutionAdapter(
            inner, _fast_policy(), cb_policy=_cb_policy(threshold=2)
        )  # type: ignore[arg-type]

        # 1st exhausted retry → 1 CB failure
        with pytest.raises(TransientAdapterError, match="net-3"):
            await resilient.get_balances()
        # 2nd exhausted retry → 2nd CB failure → CB opens
        inner.set_get_balances_effect(TransientAdapterError("net-4"))
        inner.set_get_balances_effect(TransientAdapterError("net-5"))
        inner.set_get_balances_effect(TransientAdapterError("net-6"))
        with pytest.raises(TransientAdapterError, match="net-6"):
            await resilient.get_balances()

        # Now CB OPEN
        with pytest.raises(CircuitOpenError):
            await resilient.get_balances()

    @pytest.mark.anyio
    async def test_cancel_preserves_transient_retry(self) -> None:
        """cancel_order: transient retry still works (N attempts before CB counts)."""
        inner = FakeInnerAdapter()
        # 1st cancel: transient, 2nd cancel: success (no more effects → default no-op)
        inner.set_cancel_order_effect(TransientAdapterError("net"))
        resilient = ResilientExecutionAdapter(
            inner, _fast_policy(), cb_policy=_cb_policy(threshold=5)
        )  # type: ignore[arg-type]

        # cancel_order: transient → retry → success
        await resilient.cancel_order("BTCUSDT", "v-1")
        assert inner._cancel_order_calls == 2  # 1st transient + 2nd success

    @pytest.mark.anyio
    async def test_terminal_in_place_does_not_trip_cb(self) -> None:
        """Terminal error in place_order → propagates, CB stays CLOSED."""
        from clay.execution.resilience import _CBState

        inner = FakeInnerAdapter()
        inner.set_place_effect(OrderRejectedError("rejected"))
        resilient = ResilientExecutionAdapter(
            inner, _fast_policy(), cb_policy=_cb_policy(threshold=3)
        )  # type: ignore[arg-type]
        req = _make_req()

        with pytest.raises(OrderRejectedError):
            await resilient.place_order(req)

        assert resilient._cb.state == _CBState.CLOSED
        assert len(inner._place_calls) == 1
