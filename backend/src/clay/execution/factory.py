from __future__ import annotations

import os

from clay.execution.binance_testnet import (
    BinanceTestnetExecutionClient,
    DryRunExecutionClient,
)
from clay.execution.exceptions import ExecutionConfigError
from clay.execution.protocol import ExecutionClient


def build_execution_client(*, mode: str, **overrides: object) -> "ExecutionClient":
    """Build an ``ExecutionClient`` for the requested ``mode``.

    - ``dry_run`` → ``DryRunExecutionClient`` (no-op)
    - ``testnet`` → ``BinanceTestnetExecutionClient``, requires credentials
    - ``live`` → raises ``ExecutionConfigError`` (not implemented yet)
    """
    if mode == "dry_run":
        return DryRunExecutionClient()
    if mode == "testnet":
        api_key = str(overrides.get("api_key") or os.environ.get("CLAY_BINANCE_TESTNET_API_KEY", ""))
        api_secret = str(
            overrides.get("api_secret") or os.environ.get("CLAY_BINANCE_TESTNET_API_SECRET", "")
        )
        return BinanceTestnetExecutionClient(
            api_key=api_key,
            api_secret=api_secret,
            recv_window=int(overrides.get("recv_window", 5000)),
        )
    raise ExecutionConfigError(
        "Live execution is not implemented yet. "
        "Allowed: dry_run | testnet"
    )
