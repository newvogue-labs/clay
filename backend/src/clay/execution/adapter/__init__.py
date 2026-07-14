"""Exchange Adapter layer (ADR-032 / E14 — multi-venue execution).

Pure domain — no network, no I/O, no float.
"""

from clay.execution.adapter.ccxt_base import CcxtExchangeAdapter
from clay.execution.adapter.bybit import BybitExecutionAdapter
from clay.execution.adapter.domain import (
    BalanceSnapshot,
    Fill,
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
    AdapterError,
    AmbiguousExecutionError,
    ConfigError,
    InsufficientFundsError,
    InvalidOrderError,
    OperationNotAllowedError,
    OrderRejectedError,
    TransientAdapterError,
    is_retryable,
)
from clay.execution.adapter.normalization import quantize_order, validate_order
from clay.execution.adapter.port import ExchangeAdapter
from clay.execution.adapter.rules import MarketRules

__all__ = [
    "AdapterError",
    "AmbiguousExecutionError",
    "BalanceSnapshot",
    "BybitExecutionAdapter",
    "CcxtExchangeAdapter",
    "ConfigError",
    "Environment",
    "ExchangeAdapter",
    "Fill",
    "InsufficientFundsError",
    "InvalidOrderError",
    "MarketRules",
    "OperationNotAllowedError",
    "OrderAck",
    "OrderRejectedError",
    "OrderRequest",
    "OrderSide",
    "OrderSnapshot",
    "OrderState",
    "OrderType",
    "PrecisionMode",
    "TimeInForce",
    "TransientAdapterError",
    "is_retryable",
    "quantize_order",
    "validate_order",
]
