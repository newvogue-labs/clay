"""Resilience wrapper for ExchangeAdapter (S-ADAPT-3).

Provides retry-with-reconcile for ``place_order`` and bounded
backoff-retry for read operations on ``TransientAdapterError``.

No ccxt imports — only domain + adapter.errors.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from clay.execution.adapter.domain import (
    BalanceSnapshot,
    OrderAck,
    OrderRequest,
    OrderSnapshot,
)
from clay.execution.adapter.enums import Environment
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


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for the resilience wrapper.

    All monetary/quantity fields use ``Decimal``.
    Only ``asyncio.sleep`` accepts ``float`` (delay arithmetic).
    """

    max_place_attempts: int = 2
    max_read_attempts: int = 3
    base_delay_s: Decimal = Decimal("0.5")
    max_delay_s: Decimal = Decimal("8.0")
    reconcile_skew_s: int = 5


class ResilientExecutionAdapter:
    """Wrapper that adds retry-with-reconcile around any ``ExchangeAdapter``.

    Composition over inheritance — the inner adapter is called via
    ``self._inner``, no ccxt leakage in this file.
    """

    def __init__(
        self, inner: ExchangeAdapter, policy: RetryPolicy | None = None
    ) -> None:
        self._inner = inner
        self._policy = policy or RetryPolicy()

    @property
    def environment(self) -> Environment:
        return self._inner.environment

    # -- pure domain (sync, passthrough) ------------------------------------

    def validate_order(self, req: OrderRequest, rules: MarketRules) -> None:
        self._inner.validate_order(req, rules)

    def quantize_order(self, req: OrderRequest, rules: MarketRules) -> OrderRequest:
        return self._inner.quantize_order(req, rules)

    # -- place: reconcile-before-retry (D2) ---------------------------------

    async def place_order(self, req: OrderRequest) -> OrderAck:
        """Place with reconcile-before-retry on ``AmbiguousExecutionError``.

        ``max_place_attempts`` is the ceiling on TOTAL place calls
        (initial + re-places). With the default of 2: 1 initial + 1
        re-place maximum.

        Algorithm:
        1. Try ``inner.place_order(req)`` → success ⇒ return ack.
        2. On ``AmbiguousExecutionError``:
           a. ``reconcile_orders(symbol, since=placed_at - skew)``
           b. Match by ``client_order_id``.
           c. Match found ⇒ return ``_ack_from_snapshot(match)`` (no re-place).
           d. No match + attempts remain ⇒ backoff, then re-place (same cid).
           e. No match + attempts exhausted ⇒ raise ``AmbiguousExecutionError``.
        3. Terminal errors propagate immediately.
        """
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

    # -- read: bounded backoff-retry on TransientAdapterError (D3) -----------

    async def get_market_rules(self, symbol: str) -> MarketRules:
        return await self._read_retry(lambda: self._inner.get_market_rules(symbol))

    async def get_order(self, symbol: str, venue_order_id: str) -> OrderSnapshot:
        return await self._read_retry(
            lambda: self._inner.get_order(symbol, venue_order_id)
        )

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderSnapshot]:
        return await self._read_retry(lambda: self._inner.get_open_orders(symbol))

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]:
        return await self._read_retry(
            lambda: self._inner.reconcile_orders(symbol, since)
        )

    async def get_balances(self) -> list[BalanceSnapshot]:
        return await self._read_retry(lambda: self._inner.get_balances())

    async def cancel_order(self, symbol: str, venue_order_id: str) -> None:
        return await self._read_retry(
            lambda: self._inner.cancel_order(symbol, venue_order_id)
        )

    # -- private helpers ----------------------------------------------------

    async def _read_retry(self, op):  # type: ignore[no-untyped-def]
        """Bounded backoff-retry for read operations.

        Retries only on ``TransientAdapterError``.
        Terminal errors propagate immediately.
        """
        policy = self._policy
        last_exc: BaseException | None = None

        for attempt in range(policy.max_read_attempts):
            try:
                return await op()
            except _TERMINAL_ERRORS:
                raise
            except TransientAdapterError as exc:
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
