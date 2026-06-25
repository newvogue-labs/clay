"""Tests for demo_trade_records.source column (S-REPLAY-3 — provenance)."""
from __future__ import annotations

from datetime import UTC, datetime

from clay.db.repositories_demo import DemoRepository
from clay.demo_trading.models import ProvenanceSource


def test_new_record_defaults_to_live(db_session) -> None:
    repo = DemoRepository(db_session)
    now = datetime.now(UTC)
    record = repo.create_trade_record({
        "session_id": "test-source-session",
        "signal_id": "test-source-sig",
        "symbol": "BTCUSDT",
        "executed_symbol": "BTCUSDT",
        "operator_action": "entered",
        "recorded_at": now,
        "broker_status": "awaiting_result",
    })
    db_session.commit()
    db_session.refresh(record)
    assert record.source == "live"


def test_provenance_source_literal_accepts_valid_values() -> None:
    valid: ProvenanceSource = "baseline"
    assert valid == "baseline"
    valid = "live"
    assert valid == "live"
    valid = "replay"
    assert valid == "replay"
