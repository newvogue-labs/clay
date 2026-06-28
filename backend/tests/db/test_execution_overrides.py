"""Round-trip tests for OverrideRepository + execution_overrides schema.

Covers the DB-layer only (S-EXEC-3b slice 1):
- Schema: model has the expected columns and index.
- Repository: append, list_by_override_id, latest_for_override.
- Retention regression: execution_overrides is excluded from RETENTION_WINDOWS_DAYS.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from clay.db.models_ops import ExecutionOverride
from clay.db.repositories_ops import OverrideRepository
from clay.retention.jobs import RETENTION_WINDOWS_DAYS


pytestmark = [
    pytest.mark.usefixtures("sqlite_session_factory"),
]


# === schema ===


_counter = 0


def _make_event(**overrides):
    global _counter
    _counter += 1
    defaults = {
        "event_id": f"00000000-0000-0000-0000-{_counter:012d}",
        "override_id": "override-1234-5678-90ab-cdef",
        "actor": "user@test",
        "action": "requested",
        "mode_before": None,
        "mode_after": "live",
        "expires_at": datetime(2026, 7, 1, tzinfo=UTC),
        "reason": "test",
        "created_at": datetime(2026, 6, 27, tzinfo=UTC),
        "audit_id": None,
    }
    defaults.update(overrides)
    return ExecutionOverride(**defaults)


def test_execution_overrides_tablename_and_columns() -> None:
    assert ExecutionOverride.__tablename__ == "execution_overrides"
    col_names = set(ExecutionOverride.__table__.c.keys())
    assert col_names == {
        "event_id",
        "override_id",
        "actor",
        "action",
        "mode_before",
        "mode_after",
        "expires_at",
        "reason",
        "created_at",
        "audit_id",
    }


def test_execution_overrides_has_expected_indexes() -> None:
    index_names = {idx.name for idx in ExecutionOverride.__table__.indexes}
    assert "ix_execution_overrides_override_created_at" in index_names
    assert "ix_execution_overrides_actor_created_at" in index_names


# === repository ===


def test_append_inserts_row(db_session) -> None:
    repo = OverrideRepository(db_session)
    event = _make_event()
    repo.append(event)
    db_session.commit()

    count = db_session.scalar(select(db_session.query(ExecutionOverride).count()))
    assert count == 1


def test_list_by_override_id_returns_all_events_for_an_override(db_session) -> None:
    repo = OverrideRepository(db_session)

    oid = "override-aaa"
    events = [
        _make_event(
            override_id=oid,
            action="requested",
            created_at=datetime(2026, 6, 27, 10, 0, tzinfo=UTC),
        ),
        _make_event(
            override_id=oid,
            action="confirmed",
            created_at=datetime(2026, 6, 27, 10, 1, tzinfo=UTC),
        ),
        _make_event(
            override_id="override-bbb",
            action="requested",
            created_at=datetime(2026, 6, 27, 10, 0, tzinfo=UTC),
        ),
    ]
    for e in events:
        repo.append(e)
    db_session.commit()

    result = repo.list_by_override_id(oid)
    assert len(result) == 2
    assert [e.action for e in result] == ["requested", "confirmed"]


def test_latest_for_override_returns_most_recent(db_session) -> None:
    repo = OverrideRepository(db_session)

    oid = "override-ccc"
    repo.append(
        _make_event(
            override_id=oid,
            action="requested",
            created_at=datetime(2026, 6, 27, 10, 0, tzinfo=UTC),
        )
    )
    repo.append(
        _make_event(
            override_id=oid,
            action="revoked",
            created_at=datetime(2026, 6, 27, 11, 0, tzinfo=UTC),
        )
    )
    db_session.commit()

    latest = repo.latest_for_override(oid)
    assert latest is not None
    assert latest.action == "revoked"


def test_latest_for_override_returns_none_when_missing(db_session) -> None:
    repo = OverrideRepository(db_session)
    assert repo.latest_for_override("override-zzz") is None


# === retention regression ===


def test_execution_overrides_excluded_from_retention() -> None:
    assert "execution_overrides" not in RETENTION_WINDOWS_DAYS
