"""Order lifecycle states for the ledger FSM.

Distinct from the adapter-layer ``OrderState`` — the ledger tracks
the full lifecycle from intent to terminal resolution.
"""

from __future__ import annotations

from enum import StrEnum


class LedgerState(StrEnum):
    """Finite-state states for order lifecycle tracking."""

    INTENT = "intent"
    SUBMITTING = "submitting"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLING = "cancelling"
    UNKNOWN = "unknown"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


TERMINAL_STATES: frozenset[LedgerState] = frozenset(
    {
        LedgerState.FILLED,
        LedgerState.CANCELED,
        LedgerState.REJECTED,
        LedgerState.EXPIRED,
    }
)
