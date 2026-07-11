from __future__ import annotations

from clay.execution.exceptions import OrderRejectedError


def check_order_notional(
    *,
    symbol: str,
    quantity: float,
    price: float | None,
    max_notional_usdt: float,
) -> None:
    """Pre-trade hard-block on per-order notional (S-LIVE-2).

    Off-by-default: ``max_notional_usdt <= 0.0`` disables the guard.
    Fail-closed: guard ON + unknown ``price`` (None) => reject. A real-money
    order must never bypass the cap for lack of a reference price.

    Raises:
        OrderRejectedError: notional exceeds cap, or price missing while ON.
    """
    if max_notional_usdt <= 0.0:
        return
    if price is None:
        raise OrderRejectedError(
            "order notional guard enabled but price is unknown",
            raw={"symbol": symbol, "max_notional_usdt": max_notional_usdt},
        )
    notional = abs(quantity) * price
    if notional > max_notional_usdt:
        raise OrderRejectedError(
            f"order notional {notional:.2f} USDT exceeds cap "
            f"{max_notional_usdt:.2f} USDT",
            raw={
                "symbol": symbol,
                "notional": notional,
                "max_notional_usdt": max_notional_usdt,
            },
        )
