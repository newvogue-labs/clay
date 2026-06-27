"""Tests for MP1 ops.* retention pruning.

Covers all 3 growing ops tables (ingest_runs, connector_status_history,
source_health_events) plus the flag-gating and job registration patterns.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from clay.db.models_ops import (
    AIAgentRun,
    ConnectorStatusHistory,
    IngestRun,
    SourceHealthEvent,
)
from clay.scheduler.jobs import OpsRetentionJob
from clay.retention.jobs import (
    RETENTION_WINDOWS_DAYS,
    retention_cutoff_days,
)

pytestmark = [
    pytest.mark.usefixtures("sqlite_session_factory"),
]


# --- retention window tests ---


def test_ingest_runs_retention_window_is_thirty_days() -> None:
    assert retention_cutoff_days("ingest_runs") == 30


def test_connector_status_history_window_is_180_days() -> None:
    assert retention_cutoff_days("connector_status_history") == 180


def test_source_health_events_window_is_180_days() -> None:
    assert retention_cutoff_days("source_health_events") == 180


def test_ops_only_tables_in_retention_window() -> None:
    """Only the 4 ops.* tables are in the active dict. Product/context tables
    (market_bars, news_items, sentiment_snapshots) must NOT be pruned."""
    assert set(RETENTION_WINDOWS_DAYS.keys()) == {
        "ai_agent_runs",
        "ingest_runs",
        "connector_status_history",
        "source_health_events",
    }


def test_execution_overrides_excluded_from_retention() -> None:
    """Money-gate audit table must never be auto-pruned."""
    assert "execution_overrides" not in RETENTION_WINDOWS_DAYS


# --- OpsRetentionJob prune behaviour ---


def _seed_ops_data(
    session: Session,
    *,
    old_count: int = 5,
    fresh_count: int = 3,
    table: str = "ingest_runs",
) -> None:
    """Insert *old_count* rows well past the retention window and
    *fresh_count* rows from today."""
    now = datetime.now(UTC)
    window = RETENTION_WINDOWS_DAYS[table]
    old_cutoff = now - timedelta(days=window + 1)

    for i in range(old_count):
        t = old_cutoff - timedelta(hours=i)
        if table == "ai_agent_runs":
            session.add(AIAgentRun(
                created_at=t, role_id="test", model_id="test",
                content="old", error=None,
            ))
        elif table == "ingest_runs":
            session.add(IngestRun(
                source_name="test", source_type="market",
                status="completed", started_at=t,
                finished_at=t + timedelta(seconds=10),
            ))
        elif table == "connector_status_history":
            session.add(ConnectorStatusHistory(
                connector_id="test", connector_type="news",
                status="healthy", observed_at=t,
            ))
        elif table == "source_health_events":
            session.add(SourceHealthEvent(
                source_name="test", severity="error",
                message="test", recorded_at=t,
            ))

    for i in range(fresh_count):
        t = now - timedelta(hours=i)
        if table == "ai_agent_runs":
            session.add(AIAgentRun(
                created_at=t, role_id="test", model_id="test",
                content="fresh", error=None,
            ))
        elif table == "ingest_runs":
            session.add(IngestRun(
                source_name="test", source_type="market",
                status="completed", started_at=t,
                finished_at=t + timedelta(seconds=10),
            ))
        elif table == "connector_status_history":
            session.add(ConnectorStatusHistory(
                connector_id="test", connector_type="news",
                status="healthy", observed_at=t,
            ))
        elif table == "source_health_events":
            session.add(SourceHealthEvent(
                source_name="test", severity="error",
                message="test", recorded_at=t,
            ))

    session.commit()


def _count_rows(session: Session, table: str) -> int:
    from sqlalchemy import select, func

    model_map = {
        "ai_agent_runs": AIAgentRun,
        "ingest_runs": IngestRun,
        "connector_status_history": ConnectorStatusHistory,
        "source_health_events": SourceHealthEvent,
    }
    model = model_map[table]
    result = session.scalar(select(func.count()).select_from(model))
    return result if result is not None else 0


@pytest.mark.parametrize("table", [
    "ai_agent_runs",
    "ingest_runs",
    "connector_status_history",
    "source_health_events",
])
def test_prune_removes_old_rows_keeps_fresh(
    sqlite_session_factory,
    table: str,
) -> None:
    job = OpsRetentionJob(
        session_factory=sqlite_session_factory,
        audit_writer=MagicMock(),
    )
    with sqlite_session_factory() as session:
        _seed_ops_data(session, old_count=5, fresh_count=3, table=table)

    job.run()

    with sqlite_session_factory() as session:
        remaining = _count_rows(session, table)

    assert remaining == 3, (
        f"{table}: expected 3 fresh rows after prune, got {remaining}"
    )


@pytest.mark.parametrize("table", [
    "ai_agent_runs",
    "ingest_runs",
    "connector_status_history",
    "source_health_events",
])
def test_prune_idempotent(
    sqlite_session_factory,
    table: str,
) -> None:
    """A second prune run deletes 0 additional rows (noop)."""
    job = OpsRetentionJob(
        session_factory=sqlite_session_factory,
        audit_writer=MagicMock(),
    )
    with sqlite_session_factory() as session:
        _seed_ops_data(session, old_count=5, fresh_count=0, table=table)

    job.run()  # first prune

    with sqlite_session_factory() as session:
        remaining_before = _count_rows(session, table)

    job.run()  # second prune

    with sqlite_session_factory() as session:
        remaining_after = _count_rows(session, table)

    assert remaining_after == remaining_before == 0, (
        f"{table}: idempotency failed — rows changed on second prune"
    )


def test_prune_all_four_tables(sqlite_session_factory) -> None:
    """Single run prunes all 4 tables, not just one."""
    job = OpsRetentionJob(
        session_factory=sqlite_session_factory,
        audit_writer=MagicMock(),
    )
    tables = ["ai_agent_runs", "ingest_runs", "connector_status_history", "source_health_events"]
    with sqlite_session_factory() as session:
        for table in tables:
            _seed_ops_data(session, old_count=4, fresh_count=2, table=table)

    job.run()

    with sqlite_session_factory() as session:
        for table in tables:
            remaining = _count_rows(session, table)
            assert remaining == 2, (
                f"{table}: expected 2 fresh rows, got {remaining}"
            )


def test_ops_retention_job_on_error_writes_audit_first_episode_only(
    sqlite_session_factory,
) -> None:
    """on_error writes audit on first failure, suppresses on consecutive."""
    audit_writer = MagicMock()
    job = OpsRetentionJob(
        session_factory=sqlite_session_factory,
        audit_writer=audit_writer,
    )
    exc = RuntimeError("prune failed")

    # First failure → audit written
    job.on_error(exc)
    assert audit_writer.write.call_count == 1
    call_args = audit_writer.write.call_args
    assert call_args[0][0] == "ops.retention_failed"

    # Second consecutive failure → no audit (anti-flood)
    job.on_error(RuntimeError("prune failed again"))
    assert audit_writer.write.call_count == 1  # still 1


def test_ops_retention_job_resets_failing_on_success(
    sqlite_session_factory,
) -> None:
    """After a successful run(), a new failure writes audit (new episode)."""
    audit_writer = MagicMock()
    job = OpsRetentionJob(
        session_factory=sqlite_session_factory,
        audit_writer=audit_writer,
    )
    exc = RuntimeError("prune failed")

    job.on_error(exc)
    assert audit_writer.write.call_count == 1

    # Successful run resets the failing flag
    with sqlite_session_factory() as session:
        _seed_ops_data(session, old_count=0, fresh_count=1, table="ingest_runs")
    job.run()
    assert not job._failing

    # Next failure → new audit
    job.on_error(RuntimeError("prune failed again"))
    assert audit_writer.write.call_count == 2
