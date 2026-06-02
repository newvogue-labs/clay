"""Tests for the B5 ``IngestionCycleService`` (lock + emit-gating + busy).

B5 acceptance criteria (from handoffs/b5-plan-2026-06-02.md):

1. ``test_run_once_default_emits_audit_and_bus`` — manual route path,
   ``emit=True`` (default) writes ``ingestion.run`` to audit and
   ``ingestion.updated`` to the bus **once per call**.
2. ``test_run_once_emit_false_skips_audit_and_bus`` — scheduler path,
   ``emit=False`` skips audit/bus but **persists** the DB writes
   (anti-flood correctness for the scheduler-driven case).
3. ``test_run_once_raises_busy_when_lock_held`` — concurrency:
   a second concurrent caller gets ``IngestionCycleBusy`` (the
   TOCTOU mitigation: ``asyncio.Lock`` wraps the full
   ``_do_run_once`` body).
4. ``test_freshness_state_transitions_increment_only_on_actual_change``
   — **Поправка 2** (Emma caught): first run (INSERT) → 4
   transitions; second run (UPDATE same state) → 0 transitions;
   third run (UPDATE different state) → 4 transitions. Steady
   state MUST NOT emit.
5. ``test_market_records_inserted_updated_split_correctly`` — counter
   split (MED-C): first call → all INSERT, second call → all UPDATE;
   ``market_records_written`` remains a computed property
   ``= inserted + updated`` so the pre-B5 ``assert ... == 4`` tests
   keep passing.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from clay.audit.writer import AuditWriter
from clay.db.repositories_market import MarketRepository
from clay.events.bus import EventBus
from clay.freshness.models import FreshnessResult
from clay.ingestion.context.connectors.demo_news import DemoNewsConnector
from clay.ingestion.context.connectors.demo_sentiment import DemoSentimentConnector
from clay.ingestion.context.manager import ContextConnectorManager
from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import IngestionCycleBusy, IngestionCycleService
from clay.settings.ingestion import IngestionSettings


class _FakeBinanceClient:
    """Returns a single deterministic kline per call (no real network)."""

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200):
        del symbol, interval, limit
        return [
            [
                1711954800000,
                "70250.10",
                "70420.00",
                "70180.40",
                "70390.20",
                "123.45",
                1711955699999,
                "8670000.10",
            ],
        ]


def _read_audit_events(audit_writer: AuditWriter) -> list[dict[str, Any]]:
    """Read the JSONL audit log. Returns ``[]`` if the file does not exist."""
    if not audit_writer.path.exists():
        return []
    with audit_writer.path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _drain_event_bus(event_bus: EventBus) -> list[tuple[str, dict[str, Any]]]:
    """Drain every currently-subscribed queue and return published events."""
    drained: list[tuple[str, dict[str, Any]]] = []
    for queue in list(event_bus._subscribers):  # noqa: SLF001 (test helper)
        while True:
            try:
                message = queue.get_nowait()
            except Exception:  # asyncio.QueueEmpty
                break
            drained.append((message.event_type, message.payload))
    return drained


def _build_service(
    tmp_path: Path,
    sqlite_settings: IngestionSettings,
    audit_writer: AuditWriter,
    event_bus: EventBus,
) -> IngestionCycleService:
    """Build an ``IngestionCycleService`` wired to real audit_writer + event_bus.

    Uses the SQLite-injected ``IngestionSettings`` so the SQLite
    session/DB are the ones the fixture's ``db_session`` is bound to.
    The fake binance client + demo connectors are enough to drive a
    full market+context cycle (4 market bars + 1 news + 1 sentiment).
    """
    return IngestionCycleService(
        settings=sqlite_settings,
        market_service=MarketIngestionService(_FakeBinanceClient()),
        context_manager=ContextConnectorManager(
            [DemoNewsConnector(), DemoSentimentConnector()],
        ),
        audit_writer=audit_writer,
        event_bus=event_bus,
    )


@pytest.mark.anyio
async def test_run_once_default_emits_audit_and_bus(
    db_session,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
) -> None:
    """``run_once(session)`` (default ``emit=True``) writes audit+bus once."""
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    event_bus.subscribe()  # so _drain_event_bus sees the published event
    service = _build_service(tmp_path, sqlite_settings, audit_writer, event_bus)

    summary = await service.run_once(db_session)

    # DB writes happen.
    assert summary.market_records_written == 4

    # Audit: exactly 1 ``ingestion.run`` entry.
    audits = [
        e for e in _read_audit_events(audit_writer)
        if e["event_type"] == "ingestion.run"
    ]
    assert len(audits) == 1
    assert audits[0]["payload"]["market_records_written"] == 4

    # Bus: exactly 1 ``ingestion.updated`` event.
    drained = _drain_event_bus(event_bus)
    updated = [t for t, _ in drained if t == "ingestion.updated"]
    assert len(updated) == 1
    assert updated[0] == "ingestion.updated"


@pytest.mark.anyio
async def test_run_once_emit_false_skips_audit_and_bus(
    db_session,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
) -> None:
    """``run_once(session, emit=False)`` skips audit+bus, DB writes persist.

    The scheduler-driven path: observability is the job's
    transition-only emit, not the per-tick flood. DB writes (market
    bars + freshness statuses) still happen — the cycle is the
    meaning of the job.
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    event_bus.subscribe()
    service = _build_service(tmp_path, sqlite_settings, audit_writer, event_bus)

    summary = await service.run_once(db_session, emit=False)

    # DB writes still happen.
    assert summary.market_records_written == 4
    market_repo = MarketRepository(db_session)
    assert len(market_repo.list_freshness_statuses()) == 4

    # NO audit, NO bus emission.
    assert _read_audit_events(audit_writer) == []
    assert _drain_event_bus(event_bus) == []


@pytest.mark.anyio
async def test_run_once_raises_busy_when_lock_held(
    db_session,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
) -> None:
    """A second concurrent caller gets ``IngestionCycleBusy`` (TOCTOU guard).

    Acquire the ``asyncio.Lock`` manually to simulate a first call
    in flight; the second ``run_once`` sees the locked lock and
    raises ``IngestionCycleBusy`` without entering the pipeline.
    The lock is held on the test side and released after the
    assertion so the test coroutine does not deadlock.
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    service = _build_service(tmp_path, sqlite_settings, audit_writer, event_bus)

    # Manually acquire the lock to put the service in a "busy" state.
    await service._lock.acquire()  # noqa: SLF001 (intentional — test the lock)
    try:
        with pytest.raises(IngestionCycleBusy, match="already running"):
            await service.run_once(db_session)
        # is_running is the fast non-blocking check.
        assert service.is_running is True
    finally:
        service._lock.release()  # noqa: SLF001

    # Once released, a normal call goes through.
    summary = await service.run_once(db_session)
    assert summary.market_records_written == 4
    assert service.is_running is False


@pytest.mark.anyio
async def test_freshness_state_transitions_increment_only_on_actual_change(
    db_session,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Поправка 2: ``upsert_freshness_status`` returns bool — transition signal.

    Sequence:

    1. **First run** — all 4 records INSERTed → 4 transitions.
    2. **Second run** — same ``freshness_state`` ("fresh"), only the
       ``evaluated_at``/``is_stale``/``latest_bar_open_time``
       timestamps change. ``upsert_freshness_status`` returns
       ``False`` for each → 0 transitions.
    3. **Third run** — evaluator patched to return "stale" → each
       record's state flips to "stale" → 4 transitions.

    Steady state (the 2nd run case) MUST NOT increment the
    transition counter — this is the Поправка 2 anti-flood
    correctness: in production a 60-second scheduler tick with
    unchanged data must not flood the audit log.
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    service = _build_service(tmp_path, sqlite_settings, audit_writer, event_bus)

    # Mutable state the fake evaluator closes over. Defaults to "fresh"
    # so the first run INSERTs all 4 records as "fresh".
    status_box = {"status": "fresh"}

    def _fake_evaluate(timeframe: str, last_received_at: Any, now: Any) -> FreshnessResult:
        return FreshnessResult(
            stream_name=f"market:{timeframe}",
            status=status_box["status"],
            observed_at=now,
            blocks_active_trading=status_box["status"] != "fresh",
            reason="test-fake",
        )

    monkeypatch.setattr(
        "clay.ingestion.service.evaluate_market_freshness", _fake_evaluate,
    )

    # --- Run 1: INSERT, status = "fresh" → 4 transitions ---
    status_box["status"] = "fresh"
    summary_1 = await service.run_once(db_session, emit=False)
    assert summary_1.freshness_state_transitions == 4
    assert summary_1.freshness_updates_written == 4  # informational

    # --- Run 2: UPDATE same state, status still "fresh" → 0 transitions ---
    summary_2 = await service.run_once(db_session, emit=False)
    assert summary_2.freshness_state_transitions == 0, (
        "steady-state UPDATE must NOT increment transition counter "
        "(Поправка 2 anti-flood)"
    )
    assert summary_2.freshness_updates_written == 4  # informational, still counts

    # --- Run 3: UPDATE different state, status flips to "stale" → 4 transitions ---
    status_box["status"] = "stale"
    summary_3 = await service.run_once(db_session, emit=False)
    assert summary_3.freshness_state_transitions == 4
    assert summary_3.freshness_updates_written == 4


@pytest.mark.anyio
async def test_market_records_inserted_updated_split_correctly(
    db_session,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
) -> None:
    """Counter split (MED-C): 1st run → all INSERT, 2nd run → all UPDATE.

    ``market_records_written`` stays as a computed property
    (``= inserted + updated``) so the pre-B5 ``assert ... == 4``
    contract is preserved; the new ``market_records_inserted`` and
    ``market_records_updated`` fields expose the split.
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    service = _build_service(tmp_path, sqlite_settings, audit_writer, event_bus)

    # First run — 4 new bars, all INSERTed.
    summary_1 = await service.run_once(db_session, emit=False)
    assert summary_1.market_records_inserted == 4
    assert summary_1.market_records_updated == 0
    assert summary_1.market_records_written == 4  # computed property

    # Second run — same bars, all UPDATEd.
    summary_2 = await service.run_once(db_session, emit=False)
    assert summary_2.market_records_inserted == 0
    assert summary_2.market_records_updated == 4
    assert summary_2.market_records_written == 4  # computed property

    # And the pre-B5 contract is preserved.
    market_repo = MarketRepository(db_session)
    assert len(market_repo.list_latest_bars(limit=100)) == 4
