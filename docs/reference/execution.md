# Execution

## Client Protocol

::: clay.execution.protocol
    options:
      members:
        - ExecutionClient

## Factory

::: clay.execution.factory
    options:
      members:
        - build_execution_client

## Clients (dry-run · testnet · live-stub)

::: clay.execution.binance_testnet
    options:
      members:
        - DryRunExecutionClient
        - BinanceTestnetExecutionClient
        - LiveExecutionClient

## Data Models

::: clay.execution.models

## Exceptions

::: clay.execution.exceptions
