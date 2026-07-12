from __future__ import annotations

import os
from typing import cast

from clay.execution.binance_testnet import (
    BinanceTestnetExecutionClient,
    DryRunExecutionClient,
    LiveExecutionClient,
)
from clay.execution.exceptions import ExecutionConfigError
from clay.execution.protocol import ExecutionClient


def build_execution_client(
    *, mode: str, max_order_notional_usdt: float = 0.0, **overrides: object
) -> "ExecutionClient":
    """Build an ``ExecutionClient`` for the requested ``mode``.

    - ``dry_run`` → ``DryRunExecutionClient`` (no-op)
    - ``testnet`` → ``BinanceTestnetExecutionClient``, requires credentials
    - ``live`` → ``LiveExecutionClient`` (mainnet; mode-coercion gates activation)
    """
    if mode == "dry_run":
        return DryRunExecutionClient()
    if mode == "testnet":
        api_key = str(
            overrides.get("api_key")
            or os.environ.get("CLAY_BINANCE_TESTNET_API_KEY", "")
        )
        api_secret = str(
            overrides.get("api_secret")
            or os.environ.get("CLAY_BINANCE_TESTNET_API_SECRET", "")
        )
        return BinanceTestnetExecutionClient(
            api_key=api_key,
            api_secret=api_secret,
            recv_window=cast(int, overrides.get("recv_window", 5000)),
            max_order_notional_usdt=max_order_notional_usdt,
        )
    if mode == "live":
        api_key = str(
            overrides.get("api_key") or os.environ.get("CLAY_BINANCE_LIVE_API_KEY", "")
        )
        api_secret = str(
            overrides.get("api_secret")
            or os.environ.get("CLAY_BINANCE_LIVE_API_SECRET", "")
        )
        return LiveExecutionClient(
            api_key=api_key,
            api_secret=api_secret,
            recv_window=cast(int, overrides.get("recv_window", 5000)),
            max_order_notional_usdt=max_order_notional_usdt,
        )
    raise ExecutionConfigError(
        f"Unknown execution mode {mode!r}. Allowed: dry_run | testnet | live"
    )
