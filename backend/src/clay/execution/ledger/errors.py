"""Order Ledger error taxonomy."""

from __future__ import annotations

from clay.execution.ledger.states import LedgerState


class LedgerError(Exception):
    """Base error for the order ledger layer."""


class DuplicateOrderIntentError(LedgerError):
    """An intent with this client_order_id already exists in the ledger."""


class ConcurrencyConflictError(LedgerError):
    """Optimistic-CAS failed: version mismatch on projection update."""


class IllegalTransitionError(LedgerError):
    """FSM transition is not allowed from the current state."""

    def __init__(self, from_state: LedgerState, to_state: LedgerState) -> None:
        super().__init__(f"Illegal transition: {from_state.value} -> {to_state.value}")
        self.from_state = from_state
        self.to_state = to_state


class OrderNotInLedgerError(LedgerError):
    """No projection exists for the given client_order_id."""
