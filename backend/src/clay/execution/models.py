from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OrderResult:
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
    client_order_id: str
    exchange_order_id: str
    symbol: str
    status: str


@dataclass(frozen=True)
class OrderStatus:
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
    asset: str
    free: float
    locked: float
    total: float


@dataclass(frozen=True)
class TradeFill:
    trade_id: str
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    commission: float
    commission_asset: str
    transact_time: int
