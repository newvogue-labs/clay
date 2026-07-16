"""MarketSnapshot и FreshnessPolicy — носители свежести для proof-gate.

Additive: не модифицирует MarketRules, не трогает существующий код.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from clay.execution.adapter.domain import BalanceSnapshot, OrderSnapshot
from clay.execution.adapter.rules import MarketRules


class SessionMode(StrEnum):
    """Decoupled session mode for proof-gate session invariants."""

    NORMAL = "normal"
    REDUCING = "reducing"
    HALTED = "halted"


@dataclass(frozen=True)
class MarketSnapshot:
    """Снимок рыночных правил с меткой времени и версией."""

    rules: MarketRules
    fetched_at: datetime  # aware UTC
    metadata_version: str

    def __post_init__(self) -> None:
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at должен быть aware (UTC)")

    @property
    def snapshot_hash(self) -> str:
        """Детерминированный хеш: правила-канон + version."""
        canon = json.dumps(
            {
                "min_amount": str(self.rules.min_amount),
                "max_amount": str(self.rules.max_amount),
                "min_price": str(self.rules.min_price),
                "max_price": str(self.rules.max_price),
                "min_notional": str(self.rules.min_notional),
                "amount_step": str(self.rules.amount_step),
                "price_tick": str(self.rules.price_tick),
                "metadata_version": self.metadata_version,
            },
            sort_keys=True,
        )
        return hashlib.sha256(canon.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class FreshnessPolicy:
    """Политика свежести снимка."""

    max_age_seconds: int
    expected_metadata_version: str | None = None  # None ⇒ version-check skip


@dataclass(frozen=True)
class AccountSnapshot:
    """Снимок балансов аккаунта для портфельных инвариантов."""

    balances: tuple[BalanceSnapshot, ...]
    fetched_at: datetime  # aware UTC

    def __post_init__(self) -> None:
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at должен быть aware (UTC)")

    def free_of(self, asset: str) -> Decimal:
        """Сумма free по asset; Decimal(0) если нет."""
        return sum(
            (b.free for b in self.balances if b.asset == asset),
            Decimal(0),
        )

    def total_of(self, asset: str) -> Decimal:
        """Сумма total по asset; Decimal(0) если нет."""
        return sum(
            (b.total for b in self.balances if b.asset == asset),
            Decimal(0),
        )


@dataclass(frozen=True)
class OpenOrdersSnapshot:
    """Снимок открытых ордеров для подсчёта per-symbol resting-order count."""

    orders: tuple[OrderSnapshot, ...]
    fetched_at: datetime  # aware UTC

    def __post_init__(self) -> None:
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at должен быть aware (UTC)")

    def count_for(self, symbol: str) -> int:
        """Число открытых ордеров по symbol."""
        return sum(1 for o in self.orders if o.symbol == symbol)


@dataclass(frozen=True)
class SessionSnapshot:
    """Снимок session-scoped состояния для инвариантов класса «session»."""

    kill_switch_engaged: bool
    fetched_at: datetime  # aware UTC
    mode: SessionMode = SessionMode.NORMAL
    drawdown_tripped: bool = False
    cooldown_tripped: bool = False

    def __post_init__(self) -> None:
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at должен быть aware (UTC)")
