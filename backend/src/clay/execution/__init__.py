"""Execution layer — retired legacy clients, now served by adapter layer."""

from clay.execution.adapter.binance import BinanceExecutionAdapter
from clay.execution.adapter.domain import OrderAck, OrderSnapshot
from clay.execution.adapter.enums import Environment, OrderSide, OrderState, OrderType
from clay.execution.adapter.port import ExchangeAdapter

__all__ = [
    "BinanceExecutionAdapter",
    "Environment",
    "ExchangeAdapter",
    "OrderAck",
    "OrderSide",
    "OrderSnapshot",
    "OrderState",
    "OrderType",
]
