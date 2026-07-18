"""Decision, InvariantResult, DecisionRecord — value-objects для proof-gate.

Persist (БД) приземлится в слайсе 2b. Здесь — чистые value-objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from clay.execution.proof.reason_codes import ReasonCode


class Decision(str, Enum):
    """Результат оценки: ADMIT или DENY."""

    ADMIT = "ADMIT"
    DENY = "DENY"


@dataclass(frozen=True)
class InvariantResult:
    """Результат проверки одного инварианта."""

    code: ReasonCode
    passed: bool


@dataclass(frozen=True)
class DecisionRecord:
    """Полный запись решения о допуске ордера."""

    decision: Decision
    intent_hash: str  # канон OrderRequest (Decimal→str)
    semantic_hash: str  # 经济 fingerprint БЕЗ client_order_id (D-8)
    snapshot_hash: str
    snapshot_ts: datetime
    metadata_version: str
    invariant_results: tuple[InvariantResult, ...]  # ВСЕ инварианты (collect-all)
    reason_codes: tuple[ReasonCode, ...]  # только failed
    created_at: datetime
    arming_event_id: str | None = None
