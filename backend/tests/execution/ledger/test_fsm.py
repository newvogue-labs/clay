"""Tests for order ledger FSM transition table."""

from __future__ import annotations

import pytest

from clay.execution.ledger.fsm import is_legal_transition
from clay.execution.ledger.states import LedgerState, TERMINAL_STATES


class TestTerminalStates:
    def test_four_terminal_states(self) -> None:
        assert len(TERMINAL_STATES) == 4

    def test_expected_members(self) -> None:
        assert TERMINAL_STATES == frozenset(
            {
                LedgerState.FILLED,
                LedgerState.CANCELED,
                LedgerState.REJECTED,
                LedgerState.EXPIRED,
            }
        )

    @pytest.mark.parametrize("state", list(TERMINAL_STATES))
    def test_terminal_states_no_outgoing(self, state: LedgerState) -> None:
        """Из терминального состояния нет исходящих переходов."""
        for target in LedgerState:
            assert not is_legal_transition(state, target), (
                f"terminal {state.value} -> {target.value} should be illegal"
            )


class TestLegalTransitions:
    @pytest.mark.parametrize(
        ("from_s", "to_s"),
        [
            (LedgerState.INTENT, LedgerState.SUBMITTING),
            (LedgerState.INTENT, LedgerState.UNKNOWN),
            (LedgerState.INTENT, LedgerState.REJECTED),
            (LedgerState.SUBMITTING, LedgerState.ACKNOWLEDGED),
            (LedgerState.SUBMITTING, LedgerState.PARTIALLY_FILLED),
            (LedgerState.SUBMITTING, LedgerState.FILLED),
            (LedgerState.SUBMITTING, LedgerState.REJECTED),
            (LedgerState.SUBMITTING, LedgerState.UNKNOWN),
            (LedgerState.ACKNOWLEDGED, LedgerState.PARTIALLY_FILLED),
            (LedgerState.ACKNOWLEDGED, LedgerState.FILLED),
            (LedgerState.ACKNOWLEDGED, LedgerState.CANCELLING),
            (LedgerState.ACKNOWLEDGED, LedgerState.CANCELED),
            (LedgerState.ACKNOWLEDGED, LedgerState.EXPIRED),
            (LedgerState.ACKNOWLEDGED, LedgerState.UNKNOWN),
            (LedgerState.PARTIALLY_FILLED, LedgerState.PARTIALLY_FILLED),
            (LedgerState.PARTIALLY_FILLED, LedgerState.FILLED),
            (LedgerState.PARTIALLY_FILLED, LedgerState.CANCELLING),
            (LedgerState.PARTIALLY_FILLED, LedgerState.CANCELED),
            (LedgerState.PARTIALLY_FILLED, LedgerState.EXPIRED),
            (LedgerState.PARTIALLY_FILLED, LedgerState.UNKNOWN),
            (LedgerState.CANCELLING, LedgerState.CANCELED),
            (LedgerState.CANCELLING, LedgerState.FILLED),
            (LedgerState.CANCELLING, LedgerState.PARTIALLY_FILLED),
            (LedgerState.CANCELLING, LedgerState.UNKNOWN),
            (LedgerState.UNKNOWN, LedgerState.ACKNOWLEDGED),
            (LedgerState.UNKNOWN, LedgerState.PARTIALLY_FILLED),
            (LedgerState.UNKNOWN, LedgerState.FILLED),
            (LedgerState.UNKNOWN, LedgerState.CANCELED),
            (LedgerState.UNKNOWN, LedgerState.REJECTED),
            (LedgerState.UNKNOWN, LedgerState.EXPIRED),
            (LedgerState.UNKNOWN, LedgerState.UNKNOWN),
        ],
    )
    def test_legal(self, from_s: LedgerState, to_s: LedgerState) -> None:
        assert is_legal_transition(from_s, to_s) is True


class TestIllegalTransitions:
    @pytest.mark.parametrize(
        ("from_s", "to_s"),
        [
            (LedgerState.INTENT, LedgerState.FILLED),
            (LedgerState.INTENT, LedgerState.INTENT),
            (LedgerState.INTENT, LedgerState.ACKNOWLEDGED),
            (LedgerState.INTENT, LedgerState.CANCELLING),
            (LedgerState.INTENT, LedgerState.CANCELED),
            (LedgerState.INTENT, LedgerState.EXPIRED),
            (LedgerState.INTENT, LedgerState.PARTIALLY_FILLED),
            (LedgerState.SUBMITTING, LedgerState.INTENT),
            (LedgerState.SUBMITTING, LedgerState.CANCELED),
            (LedgerState.SUBMITTING, LedgerState.CANCELLING),
            (LedgerState.SUBMITTING, LedgerState.EXPIRED),
            (LedgerState.CANCELLING, LedgerState.INTENT),
            (LedgerState.CANCELLING, LedgerState.SUBMITTING),
            (LedgerState.CANCELLING, LedgerState.ACKNOWLEDGED),
            (LedgerState.CANCELLING, LedgerState.REJECTED),
            (LedgerState.CANCELLING, LedgerState.EXPIRED),
        ],
    )
    def test_illegal(self, from_s: LedgerState, to_s: LedgerState) -> None:
        assert is_legal_transition(from_s, to_s) is False
