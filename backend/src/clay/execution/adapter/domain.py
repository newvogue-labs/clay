"""Domain DTOs for the exchange adapter layer (ADR-032).

All monetary/quantity fields are ``Decimal`` — never ``float``.
Dataclasses are frozen; containers use ``tuple`` (not ``list``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from clay.execution.adapter.enums import OrderSide, OrderState, OrderType, TimeInForce


@dataclass(frozen=True)
class OrderRequest:
    """Intent to place an order on a venue."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    time_in_force: TimeInForce
    client_order_id: str
    price: Decimal | None = None
    stop_price: Decimal | None = None


@dataclass(frozen=True)
class Fill:
    """A single matched fill within an order."""

    trade_id: str
    venue_order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal
    commission_asset: str
    transact_time: int  # ms epoch


@dataclass(frozen=True)
class OrderAck:
    """Acknowledgement of an order action (place / status query)."""

    client_order_id: str
    venue_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    state: OrderState
    quantity: Decimal
    price: Decimal | None
    transact_time: int
    fills: tuple[Fill, ...] = ()


@dataclass(frozen=True)
class OrderSnapshot:
    """Full order snapshot for get / reconcile operations."""

    client_order_id: str
    venue_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    state: OrderState
    quantity: Decimal
    executed_qty: Decimal
    price: Decimal | None
    transact_time: int
    fills: tuple[Fill, ...] = ()


@dataclass(frozen=True)
class BalanceSnapshot:
    """Asset balance snapshot."""

    asset: str
    free: Decimal
    locked: Decimal
    total: Decimal
