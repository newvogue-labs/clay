"""Execution Proof-Gate — pure checker, reason-codes, decision-record.

Дормантный: не вплетён в bootstrap/route. Live-путь байт-неизменен.
"""

from clay.execution.proof.checker import admit
from clay.execution.proof.decision import Decision, DecisionRecord, InvariantResult
from clay.execution.proof.reason_codes import ReasonCode
from clay.execution.proof.snapshot import FreshnessPolicy, MarketSnapshot

__all__ = [
    "admit",
    "Decision",
    "DecisionRecord",
    "FreshnessPolicy",
    "InvariantResult",
    "MarketSnapshot",
    "ReasonCode",
]
