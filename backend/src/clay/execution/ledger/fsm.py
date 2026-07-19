"""Order Ledger FSM — legal state transitions.

Defines the complete transition table for order lifecycle states and
a pure lookup function to validate transitions.
"""

from __future__ import annotations

from clay.execution.ledger.states import LedgerState

# Маппинг: from_state -> frozenset допустимых to_state.
# Терминальные состояния — поглощающие (нет исходящих переходов).
_TRANSITIONS: dict[LedgerState, frozenset[LedgerState]] = {
    LedgerState.INTENT: frozenset(
        {LedgerState.SUBMITTING, LedgerState.UNKNOWN, LedgerState.REJECTED}
    ),
    LedgerState.SUBMITTING: frozenset(
        {
            LedgerState.ACKNOWLEDGED,
            LedgerState.PARTIALLY_FILLED,
            LedgerState.FILLED,
            LedgerState.REJECTED,
            LedgerState.UNKNOWN,
        }
    ),
    LedgerState.ACKNOWLEDGED: frozenset(
        {
            LedgerState.PARTIALLY_FILLED,
            LedgerState.FILLED,
            LedgerState.CANCELLING,
            LedgerState.CANCELED,
            LedgerState.EXPIRED,
            LedgerState.UNKNOWN,
        }
    ),
    LedgerState.PARTIALLY_FILLED: frozenset(
        {
            LedgerState.PARTIALLY_FILLED,
            LedgerState.FILLED,
            LedgerState.CANCELLING,
            LedgerState.CANCELED,
            LedgerState.EXPIRED,
            LedgerState.UNKNOWN,
        }
    ),
    LedgerState.CANCELLING: frozenset(
        {
            LedgerState.CANCELED,
            LedgerState.FILLED,
            LedgerState.PARTIALLY_FILLED,
            LedgerState.UNKNOWN,
        }
    ),
    LedgerState.UNKNOWN: frozenset(
        {
            LedgerState.ACKNOWLEDGED,
            LedgerState.PARTIALLY_FILLED,
            LedgerState.FILLED,
            LedgerState.CANCELED,
            LedgerState.REJECTED,
            LedgerState.EXPIRED,
            LedgerState.UNKNOWN,
        }
    ),
}
# Терминальные состояния → пустой набор (поглощающие).


def is_legal_transition(from_state: LedgerState, to_state: LedgerState) -> bool:
    """Проверить, допустим ли переход ``from_state`` → ``to_state``."""
    allowed = _TRANSITIONS.get(from_state)
    if allowed is None:
        return False
    return to_state in allowed
