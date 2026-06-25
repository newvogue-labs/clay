from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ReplayTradeResult:
    session_id: str
    signal_id: str
    symbol: str
    direction: str
    entry_bar_time: datetime
    entry_price: float
    exit_price: float | None = None
    exit_bar_time: datetime | None = None
    pnl_pct: float | None = None
    outcome_status: str = "unresolved"
    reason: str = ""


@dataclass
class ReplayRunSummary:
    trades: list[ReplayTradeResult] = field(default_factory=list)
    bars_processed: int = 0
    sessions_started: int = 0
    trades_resolved: int = 0
