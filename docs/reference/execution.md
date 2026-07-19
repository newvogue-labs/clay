# Execution

## Adapter Protocol

::: clay.execution.adapter.port
    options:
      members:
        - ExchangeAdapter

## Binance Adapter

::: clay.execution.adapter.binance
    options:
      members:
        - BinanceExecutionAdapter

## Domain Types

::: clay.execution.adapter.enums
    options:
      members:
        - Environment
        - OrderSide
        - OrderType
        - TimeInForce
        - OrderState
        - PrecisionMode

## Data Models

::: clay.execution.adapter.domain
    options:
      members:
        - OrderRequest
        - Fill
        - OrderAck
        - OrderSnapshot
        - BalanceSnapshot

## Normalisation

::: clay.execution.adapter.normalization
    options:
      members:
        - validate_order
        - quantize_order

## Adapter Errors

::: clay.execution.adapter.errors
    options:
      members:
        - AdapterError
        - TransientAdapterError
        - OrderRejectedError
        - InsufficientFundsError
        - InvalidOrderError
        - ConfigError
        - AmbiguousExecutionError
        - OrderNotFoundError
        - is_retryable

## Market Rules

::: clay.execution.adapter.rules
    options:
      members:
        - MarketRules

## Order Ledger Schema

Tables in the ``ops`` schema that form the foundation of the order journal.
Schema + models only — not yet wired to any production code.

- ``order_events`` — append-only event journal (one row per state change)
- ``order_current_state`` — current-state snapshot per order
- ``fills`` — trade-level fill records

::: clay.db.models_orders
