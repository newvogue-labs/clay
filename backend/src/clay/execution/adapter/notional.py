"""Per-order notional hard-block (S-LIVE-2, ported to Decimal)."""

from __future__ import annotations

from decimal import Decimal

from clay.execution.adapter.errors import OperationNotAllowedError


def check_order_notional(
    *,
    symbol: str,
    quantity: Decimal,
    price: Decimal | None,
    max_notional: Decimal,
) -> None:
    """Pre-trade hard-block on per-order notional (S-LIVE-2).

    Off-by-default: ``max_notional <= 0`` disables the guard.
    Fail-closed: guard ON + unknown ``price`` (None) => reject. A real-money
    order must never bypass the cap for lack of a reference price.

    Raises:
        OperationNotAllowedError: notional exceeds cap, or price missing while ON.
    """
    if max_notional <= 0:
        return
    if price is None:
        raise OperationNotAllowedError(
            f"order notional guard enabled for {symbol} but price is unknown",
        )
    notional = abs(quantity) * price
    if notional > max_notional:
        raise OperationNotAllowedError(
            f"order notional {notional:.2f} exceeds cap {max_notional:.2f}",
        )