"""Resilience wrapper for ExchangeAdapter (S-ADAPT-3 + S-ADAPT-4).

Provides retry-with-reconcile for ``place_order``, bounded
backoff-retry for read operations on ``TransientAdapterError``, and
an in-house circuit breaker (daily_stock_analysis pattern).

No ccxt imports — only domain + adapter.errors.
"""

from __future__ import annotations

import asyncio
import enum
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TypeVar

from clay.execution.adapter.domain import (
    BalanceSnapshot,
    OrderAck,
    OrderRequest,
    OrderSnapshot,
)
from clay.execution.adapter.enums import Environment
from clay.execution.adapter.errors import (
    AmbiguousExecutionError,
    CircuitOpenError,
    ConfigError,
    InsufficientFundsError,
    InvalidOrderError,
    OperationNotAllowedError,
    OrderRejectedError,
    TransientAdapterError,
)
from clay.execution.adapter.port import ExchangeAdapter
from clay.execution.adapter.rules import MarketRules

T = TypeVar("T")

# Terminal errors that must propagate immediately — never retry/reconcile.
_TERMINAL_ERRORS = (
    OrderRejectedError,
    InsufficientFundsError,
    InvalidOrderError,
    ConfigError,
    OperationNotAllowedError,
)


def _ack_from_snapshot(snap: OrderSnapshot) -> OrderAck:
    """Convert an ``OrderSnapshot`` to an ``OrderAck``.

    Drops ``executed_qty`` (not present in ``OrderAck``).
    Used after reconcile-hit to avoid a redundant place call.
    """
    return OrderAck(
        client_order_id=snap.client_order_id,
        venue_order_id=snap.venue_order_id,
        symbol=snap.symbol,
        side=snap.side,
        order_type=snap.order_type,
        state=snap.state,
        quantity=snap.quantity,
        price=snap.price,
        transact_time=snap.transact_time,
        fills=snap.fills,
    )


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for retry-with-reconcile.

    All monetary/quantity fields use ``Decimal``.
    Only ``asyncio.sleep`` accepts ``float`` (delay arithmetic).
    """

    max_place_attempts: int = 2
    max_read_attempts: int = 3
    base_delay_s: Decimal = Decimal("0.5")
    max_delay_s: Decimal = Decimal("8.0")
    reconcile_skew_s: int = 5


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    """Configuration for the in-house circuit breaker.

    Trip on ``TransientAdapterError`` only.  Terminal and ambiguous
    errors pass through without affecting CB state.
    """

    failure_threshold: int = 5
    reset_timeout_s: Decimal = Decimal("30")
    half_open_max_probes: int = 1


# ---------------------------------------------------------------------------
# Circuit Breaker (in-house, async, daily_stock_analysis pattern)
# ---------------------------------------------------------------------------


class _CBState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Async circuit breaker with CLOSED / OPEN / HALF_OPEN states.

    Thread-safe via ``asyncio.Lock`` on state transitions.
    """

    def __init__(self, policy: CircuitBreakerPolicy) -> None:
        self._policy = policy
        self._state = _CBState.CLOSED
        self._consecutive_failures = 0
        self._half_open_probes = 0
        self._opened_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> _CBState:
        return self._state

    async def call(self, op: Callable[[], Awaitable[T]]) -> T:
        """Execute *op* through the circuit breaker.

        Raises ``CircuitOpenError`` immediately when OPEN.
        Trip on ``TransientAdapterError`` only — terminal / ambiguous
        errors propagate without affecting CB state.
        """
        async with self._lock:
            await self._check_open()

        try:
            result = await op()
        except TransientAdapterError as exc:
            if isinstance(exc, CircuitOpenError):
                raise  # fast-fail from CB itself, never counts
            await self._on_failure()
            raise
        except BaseException:
            # Terminal / ambiguous — passthrough, no trip
            raise
        else:
            await self._on_success()
            return result

    async def _check_open(self) -> None:
        """Transition OPEN → HALF_OPEN if reset timeout elapsed.

        In HALF_OPEN, enforce ``half_open_max_probes``: if a probe is
        already in flight (probes >= limit), reject with CircuitOpenError.
        """
        if self._state == _CBState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= float(self._policy.reset_timeout_s):
                self._state = _CBState.HALF_OPEN
                self._half_open_probes = 1  # this call is the first probe
            else:
                raise CircuitOpenError(
                    f"circuit open, retry after "
                    f"{float(self._policy.reset_timeout_s) - elapsed:.1f}s"
                )
        elif self._state == _CBState.HALF_OPEN:
            self._half_open_probes += 1
            if self._half_open_probes > self._policy.half_open_max_probes:
                raise CircuitOpenError(
                    f"half-open probe limit reached"
                    f" ({self._policy.half_open_max_probes})"
                )

    async def _on_failure(self) -> None:
        async with self._lock:
            if self._state == _CBState.HALF_OPEN:
                self._state = _CBState.OPEN
                self._opened_at = time.monotonic()
                self._half_open_probes = 0
                return
            # CLOSED
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._policy.failure_threshold:
                self._state = _CBState.OPEN
                self._opened_at = time.monotonic()

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == _CBState.HALF_OPEN:
                self._state = _CBState.CLOSED
                self._consecutive_failures = 0
                self._half_open_probes = 0
                return
            # CLOSED
            self._consecutive_failures = 0


# ---------------------------------------------------------------------------
# Resilience wrapper
# ---------------------------------------------------------------------------


class ResilientExecutionAdapter:
    """Wrapper that adds retry + reconcile + circuit-breaker.

    Composition over inheritance — the inner adapter is called via
    ``self._inner``, no ccxt leakage in this file.

    CB is outermost: ``place_order`` (entire reconcile flow),
    ``cancel_order``, and all read ops go through ``self._cb.call()``.
    ``validate`` / ``quantize`` are sync passthrough (no network).
    """

    def __init__(
        self,
        inner: ExchangeAdapter,
        policy: RetryPolicy | None = None,
        cb_policy: CircuitBreakerPolicy | None = None,
    ) -> None:
        self._inner = inner
        self._policy = policy or RetryPolicy()
        self._cb = CircuitBreaker(cb_policy or CircuitBreakerPolicy())

    @property
    def environment(self) -> Environment:
        return self._inner.environment

    # -- pure domain (sync, passthrough) ------------------------------------

    def validate_order(self, req: OrderRequest, rules: MarketRules) -> None:
        self._inner.validate_order(req, rules)

    def quantize_order(self, req: OrderRequest, rules: MarketRules) -> OrderRequest:
        return self._inner.quantize_order(req, rules)

    # -- place: CB-outermost → reconcile-before-retry -----------------------

    async def place_order(self, req: OrderRequest) -> OrderAck:
        """Place with CB + reconcile-before-retry on ``AmbiguousExecutionError``.

        ``max_place_attempts`` is the ceiling on TOTAL place calls
        (initial + re-places). With the default of 2: 1 initial + 1
        re-place maximum.
        """
        return await self._cb.call(lambda: self._place_inner(req))

    async def _place_inner(self, req: OrderRequest) -> OrderAck:
        """Inner place logic — called through CB."""
        placed_at = datetime.now(UTC)
        policy = self._policy

        try:
            return await self._inner.place_order(req)
        except _TERMINAL_ERRORS:
            raise
        except AmbiguousExecutionError:
            pass  # enter reconcile loop

        # Reconcile loop — bounded by (max_place_attempts - 1) re-places
        for _attempt in range(policy.max_place_attempts - 1):
            since = placed_at - timedelta(seconds=policy.reconcile_skew_s)
            snaps = await self._inner.reconcile_orders(req.symbol, since=since)
            match = next(
                (s for s in snaps if s.client_order_id == req.client_order_id), None
            )
            if match is not None:
                return _ack_from_snapshot(match)

            # No match — backoff then re-place with the same cid
            delay = self._backoff_delay(_attempt)
            await asyncio.sleep(float(delay))

            try:
                return await self._inner.place_order(req)
            except _TERMINAL_ERRORS:
                raise
            except AmbiguousExecutionError:
                continue  # next reconcile iteration

        # Final reconcile after loop — one last chance
        since = placed_at - timedelta(seconds=policy.reconcile_skew_s)
        snaps = await self._inner.reconcile_orders(req.symbol, since=since)
        match = next(
            (s for s in snaps if s.client_order_id == req.client_order_id), None
        )
        if match is not None:
            return _ack_from_snapshot(match)

        raise AmbiguousExecutionError(
            f"unresolved after {policy.max_place_attempts} attempts"
            f" (cid={req.client_order_id})"
        )

    # -- order-plane: cancel via CB → retry ---------------------------------

    async def cancel_order(self, symbol: str, venue_order_id: str) -> None:
        """Cancel with CB + bounded transient retry (order-plane, venue-sticky)."""
        return await self._cb.call(
            lambda: self._retry_transient(
                lambda: self._inner.cancel_order(symbol, venue_order_id)
            )
        )

    # -- read-ops: CB → retry (read path, future fallback insertion point) ---

    async def get_market_rules(self, symbol: str) -> MarketRules:
        return await self._cb.call(
            lambda: self._retry_transient(lambda: self._inner.get_market_rules(symbol))
        )

    async def get_order(self, symbol: str, venue_order_id: str) -> OrderSnapshot:
        return await self._cb.call(
            lambda: self._retry_transient(
                lambda: self._inner.get_order(symbol, venue_order_id)
            )
        )

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderSnapshot]:
        return await self._cb.call(
            lambda: self._retry_transient(lambda: self._inner.get_open_orders(symbol))
        )

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]:
        return await self._cb.call(
            lambda: self._retry_transient(
                lambda: self._inner.reconcile_orders(symbol, since)
            )
        )

    async def get_balances(self) -> list[BalanceSnapshot]:
        return await self._cb.call(
            lambda: self._retry_transient(lambda: self._inner.get_balances())
        )

    # -- private helpers ----------------------------------------------------

    async def _retry_transient(self, op):  # type: ignore[no-untyped-def]
        """Bounded backoff-retry for transient failures.

        Retries only on ``TransientAdapterError`` (excluding
        ``CircuitOpenError`` which is the CB's own fast-fail).
        Terminal errors propagate immediately.

        This is a generic retry mechanism used by both read-ops and
        cancel_order.  Not a fallback insertion point — read-fallback
        in S-ADAPT-5 wraps CB-calls for get_* ops, not this method.
        """
        policy = self._policy
        last_exc: BaseException | None = None

        for attempt in range(policy.max_read_attempts):
            try:
                return await op()
            except _TERMINAL_ERRORS:
                raise
            except TransientAdapterError as exc:
                if isinstance(exc, CircuitOpenError):
                    raise  # CB fast-fail, never retry
                last_exc = exc
                if attempt < policy.max_read_attempts - 1:
                    delay = self._backoff_delay(attempt)
                    await asyncio.sleep(float(delay))

        raise last_exc  # type: ignore[misc]

    def _backoff_delay(self, attempt: int) -> Decimal:
        """Exponential backoff: ``min(base * 2^attempt, max)``.

        Returns ``Decimal`` — caller converts to ``float`` only for
        ``asyncio.sleep``.
        """
        policy = self._policy
        delay = policy.base_delay_s * (2**attempt)
        return min(delay, policy.max_delay_s)
