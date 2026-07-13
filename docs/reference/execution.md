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
        - is_retryable

## Market Rules

::: clay.execution.adapter.rules
    options:
      members:
        - MarketRules
