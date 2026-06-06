"""Recovery path for the REVIEW-stuck FSM gap.

``complete_session`` lands the runtime in ``REVIEW`` and clears the
in-memory active session, but no code path projects the runtime
back to ``BACKGROUND_MONITORING``. ``SessionControlService.close_review``
is the explicit operator-driven recovery; this module proves it
satisfies the 5-session-in-a-row smoke and the negative guards.
"""
import pytest

from clay.runtime.states import RuntimeState

from tests.session_control.test_session_control_service import (
    build_session_service,
    seed_session_data,
)


def test_five_sessions_in_a_row_after_close_review_resets_to_idle(db_session) -> None:
    """5 full FSM cycles without process restart: start → complete → close_review.

    Each iteration must reach ``idle`` and expose ``can_start=True`` so
    the next iteration's ``start_session`` succeeds. Pre-fix, the
    second ``start`` would 409 because the runtime stayed in REVIEW.
    """
    service = build_session_service()
    seed_session_data(db_session)

    for i in range(5):
        started = service.start_session(db_session)
        assert started.lifecycle.lifecycle_state == "active_session", (
            f"iter {i}: start failed (lifecycle={started.lifecycle.lifecycle_state})"
        )
        assert started.lifecycle.can_pause is True, (
            f"iter {i}: runtime not ACTIVE_SESSION (can_pause={started.lifecycle.can_pause})"
        )

        completed = service.complete_session(db_session)
        assert completed.lifecycle.lifecycle_state == "review", (
            f"iter {i}: complete did not land in review (lifecycle={completed.lifecycle.lifecycle_state})"
        )
        assert completed.lifecycle.can_start is False, (
            f"iter {i}: can_start should be False in REVIEW"
        )

        closed = service.close_review(db_session)
        assert closed.lifecycle.lifecycle_state == "idle", (
            f"iter {i}: close_review did not land in idle (lifecycle={closed.lifecycle.lifecycle_state})"
        )
        assert closed.lifecycle.can_start is True, (
            f"iter {i}: can_start should be True after close_review"
        )
        assert service._active_session is None, (
            f"iter {i}: _active_session leaked after close_review"
        )
        assert service.runtime_manager.snapshot().state == RuntimeState.BACKGROUND_MONITORING, (
            f"iter {i}: runtime not BACKGROUND_MONITORING after close_review "
            f"(state={service.runtime_manager.snapshot().state})"
        )


def test_close_review_from_active_session_raises(db_session) -> None:
    """close_review must reject calls when runtime is ACTIVE_SESSION."""
    service = build_session_service()
    seed_session_data(db_session)
    service.start_session(db_session)
    assert service.runtime_manager.snapshot().state == RuntimeState.ACTIVE_SESSION

    with pytest.raises(ValueError, match="session is not in review"):
        service.close_review(db_session)


def test_close_review_from_idle_raises(db_session) -> None:
    """close_review must reject calls when runtime is BACKGROUND_MONITORING (idle)."""
    service = build_session_service()
    seed_session_data(db_session)
    assert service.runtime_manager.snapshot().state == RuntimeState.BACKGROUND_MONITORING

    with pytest.raises(ValueError, match="session is not in review"):
        service.close_review(db_session)
