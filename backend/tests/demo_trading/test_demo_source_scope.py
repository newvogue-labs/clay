"""Invariant tests for source_scope isolation (S-REPLAY-4 — ADR-024).

Verifies:
1.  DEFAULT_READ_SCOPE = {"baseline", "live"}
2.  Each list method respects source_scope filter
3.  Bidirectional isolation: replay ↔ baseline/live
4.  Default-scope preserves current behavior
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from clay.db.repositories_demo import DEFAULT_READ_SCOPE, DemoRepository
from clay.db.models_demo import DemoTradeRecord


def _make_record(session, source: str, session_id: str = "s1") -> DemoTradeRecord:
    now = datetime.now(UTC)
    record = DemoTradeRecord(
        session_id=session_id,
        signal_id=f"sig-{session_id}",
        symbol="BTCUSDT",
        executed_symbol="BTCUSDT",
        operator_action="entered",
        recorded_at=now,
        broker_status="closed",
        outcome_status="matched",
        source=source,
    )
    session.add(record)
    session.flush()
    return record


def test_default_scope_contains_baseline_and_live() -> None:
    assert DEFAULT_READ_SCOPE == frozenset({"baseline", "live"})


def test_default_scope_excludes_replay() -> None:
    assert "replay" not in DEFAULT_READ_SCOPE


def test_list_all_trade_records_respects_scope(db_session) -> None:
    _make_record(db_session, source="baseline")
    _make_record(db_session, source="live")
    _make_record(db_session, source="replay")
    db_session.commit()

    repo = DemoRepository(db_session)

    default = repo.list_all_trade_records()
    assert len(default) == 2

    replay = repo.list_all_trade_records(source_scope={"replay"})
    assert len(replay) == 1
    assert replay[0].source == "replay"

    isolated = repo.list_all_trade_records(source_scope={"baseline"})
    assert len(isolated) == 1
    assert isolated[0].source == "baseline"


def test_list_trade_records_respects_scope(db_session) -> None:
    _make_record(db_session, source="baseline")
    _make_record(db_session, source="live")
    _make_record(db_session, source="replay")
    db_session.commit()

    repo = DemoRepository(db_session)

    default = repo.list_trade_records()
    assert len(default) == 2

    replay = repo.list_trade_records(source_scope={"replay"})
    assert len(replay) == 1


def test_list_resolved_window_respects_scope(db_session) -> None:
    _make_record(db_session, source="baseline")
    _make_record(db_session, source="replay")
    db_session.commit()

    repo = DemoRepository(db_session)

    default = repo.list_resolved_window(hours=24)
    assert len(default) == 1

    replay = repo.list_resolved_window(hours=24, source_scope={"replay"})
    assert len(replay) == 1
    assert replay[0].source == "replay"


def test_list_ordered_recent_respects_scope(db_session) -> None:
    _make_record(db_session, source="live")
    _make_record(db_session, source="replay")
    db_session.commit()

    repo = DemoRepository(db_session)

    default = repo.list_ordered_recent()
    assert len(default) == 1

    replay = repo.list_ordered_recent(source_scope={"replay"})
    assert len(replay) == 1
    assert replay[0].source == "replay"


def test_list_open_positions_respects_scope(db_session) -> None:
    for src in ("baseline", "live", "replay"):
        now = datetime.now(UTC)
        db_session.add(
            DemoTradeRecord(
                session_id=f"s-{src}",
                signal_id=f"sig-{src}",
                symbol="BTCUSDT",
                executed_symbol="BTCUSDT",
                operator_action="entered",
                recorded_at=now,
                broker_status="awaiting_result",
                outcome_status="unresolved",
                source=src,
            )
        )
    db_session.commit()

    repo = DemoRepository(db_session)

    default = repo.list_open_positions()
    assert len(default) == 2

    replay = repo.list_open_positions(source_scope={"replay"})
    assert len(replay) == 1
    assert replay[0].source == "replay"


def test_list_session_trades_respects_scope(db_session) -> None:
    for src in ("baseline", "replay"):
        _make_record(db_session, source=src, session_id=f"session-{src}")
    db_session.commit()

    repo = DemoRepository(db_session)

    baseline = repo.list_session_trades(session_id="session-baseline")
    assert len(baseline) == 1
    assert baseline[0].source == "baseline"

    replay = repo.list_session_trades(
        session_id="session-replay", source_scope={"replay"}
    )
    assert len(replay) == 1
    assert replay[0].source == "replay"


def test_bidirectional_isolation(db_session) -> None:
    _make_record(db_session, source="baseline")
    _make_record(db_session, source="live")
    _make_record(db_session, source="replay")
    db_session.commit()

    repo = DemoRepository(db_session)

    baseline_live = {
        r.id for r in repo.list_all_trade_records(source_scope={"baseline", "live"})
    }
    replay = {r.id for r in repo.list_all_trade_records(source_scope={"replay"})}

    assert len(baseline_live) == 2
    assert len(replay) == 1
    assert not (baseline_live & replay), "scope sets must not overlap"


def test_empty_scope_list_resolved_window_raises(db_session) -> None:
    """Empty set() on risk-limit method → ValueError (fail-closed)."""
    repo = DemoRepository(db_session)
    with pytest.raises(ValueError, match="source_scope must be non-empty"):
        repo.list_resolved_window(hours=24, source_scope=set())


def test_empty_scope_list_all_trade_records_raises(db_session) -> None:
    """Empty set() on calibration method → ValueError (fail-closed)."""
    repo = DemoRepository(db_session)
    with pytest.raises(ValueError, match="source_scope must be non-empty"):
        repo.list_all_trade_records(source_scope=set())


def test_empty_scope_frozenset_raises(db_session) -> None:
    """Empty frozenset() → ValueError."""
    repo = DemoRepository(db_session)
    with pytest.raises(ValueError, match="source_scope must be non-empty"):
        repo.list_open_positions(source_scope=frozenset())


def test_default_scope_leggitimate_values_pass(db_session) -> None:
    """Legitimate scopes pass validation: DEFAULT, {replay}, {baseline}, mix."""
    repo = DemoRepository(db_session)
    repo.list_all_trade_records(source_scope=DEFAULT_READ_SCOPE)  # implicit default
    repo.list_all_trade_records(source_scope={"replay"})
    repo.list_all_trade_records(source_scope={"baseline"})
    repo.list_resolved_window(hours=24, source_scope={"baseline", "replay"})


def test_default_scope_matches_current_behavior(db_session) -> None:
    _make_record(db_session, source="baseline")
    _make_record(db_session, source="live")
    _make_record(db_session, source="replay")
    db_session.commit()

    repo = DemoRepository(db_session)

    explicit = repo.list_all_trade_records(source_scope={"baseline", "live"})
    implicit = repo.list_all_trade_records()

    assert len(explicit) == len(implicit)
    assert {r.id for r in explicit} == {r.id for r in implicit}
