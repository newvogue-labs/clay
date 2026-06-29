"""Round-trip tests for the 6 ops runtime-state repositories + UTCDateTime.

Exercises the 6 classes in ``clay.db.repositories_runtime_state`` against
the SQLite test database (see ``tests/conftest.py``). Service layer is
not touched — this slice is the repository layer only.

Slice A2.5 (2026-06-01): the 6 runtime-state tables now use
``UTCDateTime`` so round-tripped timestamps stay timezone-aware on
SQLite. The asserts here compare against tz-aware values directly (no
``.replace(tzinfo=None)`` workarounds) and there is a small unit-test
block at the bottom that pins down the decorator contract.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import DateTime, func, select

from clay.db.models_ops import (
    AIAssignment,
    AIControlState,
    ReliabilityState,
    SessionState,
    StrategyState,
    WorkspaceFocus,
)
from clay.db.repositories_runtime_state import (
    AIAssignmentRepository,
    AIControlStateRepository,
    ReliabilityStateRepository,
    SessionStateRepository,
    StrategyStateRepository,
    WorkspaceFocusRepository,
    INITIAL_ASSIGNMENTS,
)
from clay.db.types import UTCDateTime


# === AIAssignmentRepository (multi-row) ===


def test_ai_assignment_repository_starts_empty(db_session) -> None:
    repo = AIAssignmentRepository(db_session)
    assert repo.read_all() == {}


def test_ai_assignment_repository_bulk_upsert_seeds_initial_map(db_session) -> None:
    repo = AIAssignmentRepository(db_session)
    repo.bulk_upsert(INITIAL_ASSIGNMENTS)
    db_session.commit()

    assert repo.read_all() == INITIAL_ASSIGNMENTS
    assert db_session.scalar(select(func.count()).select_from(AIAssignment)) == 4


def test_ai_assignment_repository_upsert_updates_existing_role(db_session) -> None:
    repo = AIAssignmentRepository(db_session)
    repo.upsert("chief-agent", "minimax-m3")
    db_session.commit()

    repo.upsert("chief-agent", "openai-gpt-5.5")
    db_session.commit()

    assert repo.read_all() == {"chief-agent": "openai-gpt-5.5"}
    assert db_session.scalar(select(func.count()).select_from(AIAssignment)) == 1


def test_ai_assignment_repository_upsert_does_not_duplicate_rows(db_session) -> None:
    repo = AIAssignmentRepository(db_session)
    repo.upsert("chief-agent", "minimax-m3")
    repo.upsert("chief-agent", "minimax-m3")
    repo.upsert("chief-agent", "minimax-m3")
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(AIAssignment)) == 1
    assert repo.read_all() == {"chief-agent": "minimax-m3"}


def test_ai_assignment_repository_updated_at_is_tz_aware_and_recent(db_session) -> None:
    repo = AIAssignmentRepository(db_session)
    before = datetime.now(UTC)
    repo.upsert("chief-agent", "minimax-m3")
    db_session.commit()
    after = datetime.now(UTC)

    row = db_session.get(AIAssignment, "chief-agent")
    assert row is not None
    assert row.updated_at.tzinfo is not None
    assert before <= row.updated_at <= after


# === AIControlStateRepository (singleton) ===


def test_ai_control_state_get_or_create_creates_id_one_row(db_session) -> None:
    repo = AIControlStateRepository(db_session)
    row = repo.get_or_create()
    db_session.commit()

    assert row.id == 1
    assert row.last_reviewed_at is None
    assert row.pending_review_id is None
    assert db_session.scalar(select(func.count()).select_from(AIControlState)) == 1


def test_ai_control_state_get_or_create_is_idempotent(db_session) -> None:
    repo = AIControlStateRepository(db_session)
    row1 = repo.get_or_create()
    db_session.commit()
    row2 = repo.get_or_create()
    db_session.commit()

    assert row1 is row2
    assert db_session.scalar(select(func.count()).select_from(AIControlState)) == 1


def test_ai_control_state_round_trip_pending_review(db_session) -> None:
    repo = AIControlStateRepository(db_session)
    ts = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    repo.save(
        last_reviewed_at=ts,
        pending_review_id="rev-1",
        pending_review_role_id="chief-agent",
        pending_review_model_id="minimax-m3",
        pending_review_created_at=ts,
    )
    db_session.commit()

    row = repo.read()
    assert row is not None
    assert row.last_reviewed_at == ts
    assert row.last_reviewed_at is not None
    assert row.last_reviewed_at.tzinfo is not None
    assert row.pending_review_id == "rev-1"
    assert row.pending_review_role_id == "chief-agent"
    assert row.pending_review_model_id == "minimax-m3"
    assert row.pending_review_created_at == ts
    assert row.pending_review_created_at is not None
    assert row.pending_review_created_at.tzinfo is not None


def test_ai_control_state_save_can_clear_nullable_fields(db_session) -> None:
    repo = AIControlStateRepository(db_session)
    repo.save(pending_review_id="rev-1", pending_review_role_id="chief-agent")
    db_session.commit()
    row = repo.read()
    assert row is not None
    assert row.pending_review_id == "rev-1"

    repo.save(pending_review_id=None, pending_review_role_id=None)
    db_session.commit()
    row = repo.read()
    assert row is not None
    assert row.pending_review_id is None
    assert row.pending_review_role_id is None


# === SessionStateRepository (singleton, all fields nullable) ===


def test_session_state_get_or_create_creates_empty_row(db_session) -> None:
    repo = SessionStateRepository(db_session)
    row = repo.get_or_create()
    db_session.commit()

    assert row.id == 1
    assert row.session_id is None
    assert row.current_pair_symbol is None
    assert row.paused_at is None


def test_session_state_round_trip_active_and_pending(db_session) -> None:
    repo = SessionStateRepository(db_session)
    started = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    paused = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    pending_created = datetime(2026, 6, 1, 13, 30, tzinfo=UTC)
    repo.save(
        session_id="sess-1",
        current_pair_symbol="BTCUSDT",
        current_signal_id="sig-1",
        strategy_mode="momentum",
        started_at=started,
        paused_at=paused,
        pending_replacement_id="rep-1",
        pending_current_symbol="BTCUSDT",
        pending_proposed_symbol="ETHUSDT",
        pending_created_at=pending_created,
    )
    db_session.commit()

    row = repo.read()
    assert row is not None
    assert row.session_id == "sess-1"
    assert row.current_pair_symbol == "BTCUSDT"
    assert row.current_signal_id == "sig-1"
    assert row.strategy_mode == "momentum"
    assert row.started_at == started
    assert row.started_at is not None
    assert row.started_at.tzinfo is not None
    assert row.paused_at == paused
    assert row.paused_at is not None
    assert row.paused_at.tzinfo is not None
    assert row.pending_replacement_id == "rep-1"
    assert row.pending_current_symbol == "BTCUSDT"
    assert row.pending_proposed_symbol == "ETHUSDT"
    assert row.pending_created_at == pending_created
    assert row.pending_created_at is not None
    assert row.pending_created_at.tzinfo is not None


# === WorkspaceFocusRepository (singleton, with focus_source default) ===


def test_workspace_focus_get_or_create_applies_default_focus_source(db_session) -> None:
    repo = WorkspaceFocusRepository(db_session)
    row = repo.get_or_create()
    db_session.commit()

    assert row.id == 1
    assert row.focus_source == "system_recommendation"
    assert row.focus_symbol is None
    assert row.selected_signal_id is None


def test_workspace_focus_round_trip_changes_focus_and_source(db_session) -> None:
    repo = WorkspaceFocusRepository(db_session)
    repo.save(focus_symbol="BTCUSDT", focus_source="user")
    db_session.commit()

    row = repo.read()
    assert row is not None
    assert row.focus_symbol == "BTCUSDT"
    assert row.focus_source == "user"
    assert row.selected_signal_id is None


def test_workspace_focus_updated_at_advances_on_save(db_session) -> None:
    repo = WorkspaceFocusRepository(db_session)
    row1 = repo.get_or_create()
    db_session.commit()
    initial = row1.updated_at

    time.sleep(0.01)
    repo.save(focus_symbol="ETHUSDT")
    db_session.commit()

    row2 = repo.read()
    assert row2 is not None
    assert row2.updated_at > initial


# === StrategyStateRepository (singleton, with strategy_mode default) ===


def test_strategy_state_get_or_create_applies_default_momentum(db_session) -> None:
    repo = StrategyStateRepository(db_session)
    row = repo.get_or_create()
    db_session.commit()

    assert row.id == 1
    assert row.strategy_mode == "momentum"


def test_strategy_state_round_trip_changes_mode(db_session) -> None:
    repo = StrategyStateRepository(db_session)
    repo.save(strategy_mode="mean_reversion")
    db_session.commit()

    row = repo.read()
    assert row is not None
    assert row.strategy_mode == "mean_reversion"


def test_strategy_state_updated_at_advances_on_save(db_session) -> None:
    repo = StrategyStateRepository(db_session)
    row1 = repo.get_or_create()
    db_session.commit()
    initial = row1.updated_at

    time.sleep(0.01)
    repo.save(strategy_mode="breakout")
    db_session.commit()

    row2 = repo.read()
    assert row2 is not None
    assert row2.updated_at > initial


# === ReliabilityStateRepository (singleton, simple) ===


def test_reliability_state_get_or_create_creates_empty_row(db_session) -> None:
    repo = ReliabilityStateRepository(db_session)
    row = repo.get_or_create()
    db_session.commit()

    assert row.id == 1
    assert row.last_rechecked_at is None


def test_reliability_state_round_trip_timestamp(db_session) -> None:
    repo = ReliabilityStateRepository(db_session)
    ts = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
    repo.save(last_rechecked_at=ts)
    db_session.commit()

    row = repo.read()
    assert row is not None
    assert row.last_rechecked_at == ts
    assert row.last_rechecked_at is not None
    assert row.last_rechecked_at.tzinfo is not None


# === Cross-cutting: get_or_create is idempotent across all 5 singletons ===

SINGLETON_MODEL_BY_REPO: dict[type, type] = {
    AIControlStateRepository: AIControlState,
    SessionStateRepository: SessionState,
    WorkspaceFocusRepository: WorkspaceFocus,
    StrategyStateRepository: StrategyState,
    ReliabilityStateRepository: ReliabilityState,
}


@pytest.mark.parametrize("repo_class", list(SINGLETON_MODEL_BY_REPO))
def test_singleton_get_or_create_is_idempotent(db_session, repo_class) -> None:
    repo = repo_class(db_session)
    model_class = SINGLETON_MODEL_BY_REPO[repo_class]

    row1 = repo.get_or_create()
    db_session.commit()
    row2 = repo.get_or_create()
    db_session.commit()

    assert row1.id == row2.id == 1
    assert db_session.scalar(select(func.count()).select_from(model_class)) == 1


# === UTCDateTime decorator (Slice A2.5)


def test_utc_datetime_naive_bind_param_is_treated_as_utc() -> None:
    decorator = UTCDateTime()
    naive = datetime(2026, 6, 1, 12, 0)
    bound = decorator.process_bind_param(naive, dialect=None)
    assert bound == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    assert bound is not None
    assert bound.tzinfo is UTC


def test_utc_datetime_aware_non_utc_bind_param_is_converted_to_utc() -> None:
    decorator = UTCDateTime()
    plus3 = timezone(timedelta(hours=3))
    aware_non_utc = datetime(2026, 6, 1, 15, 0, tzinfo=plus3)  # 12:00 UTC
    bound = decorator.process_bind_param(aware_non_utc, dialect=None)
    assert bound == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    assert bound is not None
    assert bound.tzinfo is UTC


def test_utc_datetime_naive_result_is_tagged_as_utc() -> None:
    decorator = UTCDateTime()
    naive = datetime(2026, 6, 1, 12, 0)
    result = decorator.process_result_value(naive, dialect=None)
    assert result == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    assert result is not None
    assert result.tzinfo is UTC


def test_utc_datetime_aware_result_is_converted_to_utc() -> None:
    decorator = UTCDateTime()
    plus3 = timezone(timedelta(hours=3))
    aware_non_utc = datetime(2026, 6, 1, 15, 0, tzinfo=plus3)
    result = decorator.process_result_value(aware_non_utc, dialect=None)
    assert result == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    assert result is not None
    assert result.tzinfo is UTC


def test_utc_datetime_none_passes_through_on_both_sides() -> None:
    decorator = UTCDateTime()
    assert decorator.process_bind_param(None, dialect=None) is None
    assert decorator.process_result_value(None, dialect=None) is None


def test_utc_datetime_impl_is_timezone_aware_datetime_and_caches() -> None:
    impl = UTCDateTime.impl
    assert isinstance(impl, DateTime)
    assert impl.timezone is True
    assert UTCDateTime.cache_ok is True
