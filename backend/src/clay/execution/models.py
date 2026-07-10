from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OrderResult:
    """Immutable snapshot returned after placing an order.

    Captures the exchange response at the moment of submission.  Fill
    details may be partial — see TradeFill for per-fill granularity.
    """

    client_order_id: str
    exchange_order_id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    status: str
    transact_time: int  # ms epoch
    price: float | None = None
    stop_price: float | None = None
    fills: list[TradeFill] = field(default_factory=list)


@dataclass(frozen=True)
class CancelResult:
    """Immutable snapshot returned after cancelling an order.

    If the order was not found on the exchange, ``status`` is
    ``"not_found"`` and ``exchange_order_id`` still carries the requested
    ID for traceability.
    """

    client_order_id: str
    exchange_order_id: str
    symbol: str
    status: str


@dataclass(frozen=True)
class OrderStatus:
    """Immutable snapshot of an order's current state on the exchange.

    Returned by ExecutionClient.get_order_status and
    ExecutionClient.get_open_orders.  ``executed_qty`` tracks partial
    fills against the requested ``quantity``.
    """

    client_order_id: str
    exchange_order_id: str
    symbol: str
    side: str
    order_type: str
    status: str
    quantity: float
    executed_qty: float
    price: float | None = None
    stop_price: float | None = None
    transact_time: int | None = None


@dataclass(frozen=True)
class Balance:
    """Immutable snapshot of a single asset balance.

    ``free`` is the available amount; ``locked`` is held in open orders;
    ``total`` = free + locked.
    """

    asset: str
    free: float
    locked: float
    total: float


@dataclass(frozen=True)
class TradeFill:
    """Immutable snapshot of a single trade fill (execution event).

    Represents one matched fill within an order.  ``transact_time`` is
    millisecond epoch (exchange-reported timestamp).
    """

    trade_id: str
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    commission: float
    commission_asset: str
    transact_time: int
