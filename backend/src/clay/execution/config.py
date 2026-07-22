from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from decimal import Decimal

from clay.execution.adapter.enums import Environment

logger = logging.getLogger(__name__)


def environment_from_mode(mode: str) -> Environment | None:
    """Map legacy execution mode string to adapter ``Environment``.

    Returns ``None`` for modes that must NOT build a live adapter
    (``dry_run``, ``live`` without override, unknown).
    """
    if mode == "testnet":
        return Environment.TESTNET
    return None


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
    max_order_notional_usdt: Decimal = Decimal("0")
    proof_max_position_usdt: Decimal = Decimal("0")
    proof_max_open_orders: int = 0
    proof_enforce_session: bool = False
    proof_enforce_session_risk: bool = False
    proof_enforce_halt_latch: bool = False
    proof_enforce_portfolio: bool = False
    proof_max_snapshot_age_seconds: int = 30
    proof_metadata_version: str = "v1"
    proof_submit_rate_max: int = 0
    proof_submit_rate_window_seconds: int = 0
    proof_duplicate_intent_window_seconds: int = 0
    order_ledger_enabled: bool = False

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
            max_order_notional_usdt=Decimal(
                os.environ.get("CLAY_EXECUTION_MAX_ORDER_NOTIONAL", "0")
            ),
            proof_max_position_usdt=Decimal(
                os.environ.get("CLAY_PROOF_MAX_POSITION_USDT", "0")
            ),
            proof_max_open_orders=int(
                os.environ.get("CLAY_PROOF_MAX_OPEN_ORDERS", "0")
            ),
            proof_enforce_session=os.environ.get(
                "CLAY_PROOF_ENFORCE_SESSION", "0"
            ).lower()
            in {"1", "true"},
            proof_enforce_session_risk=os.environ.get(
                "CLAY_PROOF_ENFORCE_SESSION_RISK", "0"
            ).lower()
            in {"1", "true"},
            proof_enforce_halt_latch=os.environ.get(
                "CLAY_PROOF_ENFORCE_HALT_LATCH", "0"
            ).lower()
            in {"1", "true"},
            proof_enforce_portfolio=os.environ.get(
                "CLAY_PROOF_ENFORCE_PORTFOLIO", "0"
            ).lower()
            in {"1", "true"},
            proof_max_snapshot_age_seconds=int(
                os.environ.get("CLAY_PROOF_MAX_SNAPSHOT_AGE_SECONDS", "30")
            ),
            proof_metadata_version=os.environ.get("CLAY_PROOF_METADATA_VERSION", "v1"),
            proof_submit_rate_max=int(
                os.environ.get("CLAY_PROOF_SUBMIT_RATE_MAX", "0")
            ),
            proof_submit_rate_window_seconds=int(
                os.environ.get("CLAY_PROOF_SUBMIT_RATE_WINDOW_SECONDS", "0")
            ),
            proof_duplicate_intent_window_seconds=int(
                os.environ.get("CLAY_PROOF_DUPLICATE_INTENT_WINDOW_SECONDS", "0")
            ),
            order_ledger_enabled=os.environ.get(
                "CLAY_ORDER_LEDGER_ENABLED", "0"
            ).lower()
            in {"1", "true"},
        )
