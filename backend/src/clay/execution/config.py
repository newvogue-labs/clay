from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionConfig:
    mode: str = "dry_run"
    exchange_id: str = "binance_spot"
    base_url: str = ""
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = False
    recv_window: int = 5000
    allow_live_override: bool = False
    max_order_notional_usdt: float = 0.0

    @classmethod
    def from_env(cls) -> ExecutionConfig:
        mode = os.environ.get("CLAY_EXECUTION_MODE", "dry_run")
        if mode not in {"dry_run", "testnet"}:
            logger.warning(
                "CLAY_EXECUTION_MODE=%r rejected, defaulting to dry_run", mode
            )
            mode = "dry_run"
        return cls(
            mode=mode,
            exchange_id=os.environ.get("CLAY_EXECUTION_EXCHANGE_ID", "binance_spot"),
            base_url=os.environ.get("CLAY_EXECUTION_BASE_URL", ""),
            api_key=os.environ.get("CLAY_BINANCE_TESTNET_API_KEY", ""),
            api_secret=os.environ.get("CLAY_BINANCE_TESTNET_API_SECRET", ""),
            testnet=os.environ.get("CLAY_EXECUTION_TESTNET", "false").lower() == "true",
            recv_window=int(os.environ.get("CLAY_EXECUTION_RECV_WINDOW", "5000")),
            allow_live_override=os.environ.get(
                "CLAY_EXECUTION_ALLOW_LIVE_OVERRIDE", "false"
            ).lower()
            == "true",
            max_order_notional_usdt=float(
                os.environ.get("CLAY_EXECUTION_MAX_ORDER_NOTIONAL", "0")
            ),
        )
