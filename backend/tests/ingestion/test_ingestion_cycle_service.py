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

import json
import threading
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
from clay.ingestion.market.exchange_config import ExchangeConfig
from clay.ingestion.market.models import NormalizedMarketBar
from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import (
    IngestionCycleBusy,
    IngestionCycleService,
    IngestionRunSummary,
    _CollectedData,
)
from clay.settings.ingestion import IngestionSettings


class _FakeBinanceClient:
    """Returns a single deterministic kline per call (no real network).

    E1: conforms to ``MarketDataClient`` protocol — returns
    ``NormalizedMarketBar`` instead of raw arrays.
    """

    source: str = "test"

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200):
        del limit
        return [
            NormalizedMarketBar(
                symbol=symbol or "BTCUSDT",
                timeframe=interval or "5m",
                open=70250.10,
                high=70420.00,
                low=70180.40,
                close=70390.20,
                volume=123.45,
                quote_volume=8670000.10,
                source="binance_spot",
                bar_open_time=datetime(2024, 4, 1, 7, 0, tzinfo=UTC),
                bar_close_time=datetime(2024, 4, 1, 7, 14, 59, 999000, tzinfo=UTC),
            ),
        ]

    def set_http_client(self, client: object | None) -> None:
        return


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
    sqlite_session_factory: Any,
    sqlite_settings: IngestionSettings,
    audit_writer: AuditWriter,
    event_bus: EventBus,
) -> IngestionCycleService:
    """Build an ``IngestionCycleService`` wired to real audit_writer + event_bus.

    C3: ``session_factory`` is required — the service opens **its own**
    ``Session`` inside ``_persist`` (worker thread). The fake binance
    client + demo connectors are enough to drive a full market+context
    cycle (4 market bars + 1 news + 1 sentiment).
    """
    client = _FakeBinanceClient()
    exchange_config = ExchangeConfig(
        exchange_id="test",
        source=client.source,
        enabled=True,
        base_url="http://fake",
        symbols=list(sqlite_settings.market_symbols),
        timeframes=list(sqlite_settings.market_timeframes),
    )
    return IngestionCycleService(
        settings=sqlite_settings,
        market_service=MarketIngestionService({"test": (client, exchange_config)}),
        context_manager=ContextConnectorManager(
            [DemoNewsConnector(), DemoSentimentConnector()],
        ),
        session_factory=sqlite_session_factory,
        audit_writer=audit_writer,
        event_bus=event_bus,
    )


@pytest.mark.anyio
async def test_run_once_default_emits_audit_and_bus(
    sqlite_session_factory,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
) -> None:
    """``run_once(emit=True)`` (default) writes audit+bus once.

    C3: session lifecycle is owned by the service —
    the caller no longer provides a ``session``.
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    event_bus.subscribe()
    service = _build_service(
        sqlite_session_factory, sqlite_settings, audit_writer, event_bus
    )

    summary = await service.run_once(emit=True)

    # DB writes happen.
    assert summary.market_records_written == 4

    # Audit: exactly 1 ``ingestion.run`` entry.
    audits = [
        e
        for e in _read_audit_events(audit_writer)
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
    sqlite_session_factory,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
) -> None:
    """``run_once(emit=False)`` skips audit+bus, DB writes persist.

    The scheduler-driven path: observability is the job's
    transition-only emit, not the per-tick flood. DB writes (market
    bars + freshness statuses) still happen — the cycle is the
    meaning of the job.

    C3: verify DB writes via a **separate** session — the service
    owns its own session inside ``_persist`` (worker thread).
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    event_bus.subscribe()
    service = _build_service(
        sqlite_session_factory, sqlite_settings, audit_writer, event_bus
    )

    summary = await service.run_once(emit=False)

    # DB writes still happen — verify via separate session.
    assert summary.market_records_written == 4
    with sqlite_session_factory() as session:
        market_repo = MarketRepository(session)
        assert len(market_repo.list_freshness_statuses()) == 4

        # E2: freshness records carry source from the data path (latest_bar.source),
        # not from a hardcoded literal.
        from clay.db.models_market import MarketFreshnessStatus
        from sqlalchemy import select

        freshness_rows = session.scalars(select(MarketFreshnessStatus)).all()
        for row in freshness_rows:
            assert row.source == "binance_spot"

    # NO audit, NO bus emission.
    assert _read_audit_events(audit_writer) == []
    assert _drain_event_bus(event_bus) == []


@pytest.mark.anyio
async def test_run_once_raises_busy_when_lock_held(
    sqlite_session_factory,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
) -> None:
    """A second concurrent caller gets ``IngestionCycleBusy`` (TOCTOU guard).

    Acquire the ``asyncio.Lock`` manually to simulate a first call
    in flight; the second ``run_once`` sees the locked lock and
    raises ``IngestionCycleBusy`` without entering the pipeline.
    The lock is held on the test side and released after the
    assertion so the test coroutine does not deadlock.

    C3: ``run_once`` no longer takes a session parameter.
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    service = _build_service(
        sqlite_session_factory, sqlite_settings, audit_writer, event_bus
    )

    # Manually acquire the lock to put the service in a "busy" state.
    await service._lock.acquire()  # noqa: SLF001 (intentional — test the lock)
    try:
        with pytest.raises(IngestionCycleBusy, match="already running"):
            await service.run_once()
        # is_running is the fast non-blocking check.
        assert service.is_running is True
    finally:
        service._lock.release()  # noqa: SLF001

    # Once released, a normal call goes through.
    summary = await service.run_once()
    assert summary.market_records_written == 4
    assert service.is_running is False


@pytest.mark.anyio
async def test_freshness_state_transitions_increment_only_on_actual_change(
    sqlite_session_factory,
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
    service = _build_service(
        sqlite_session_factory, sqlite_settings, audit_writer, event_bus
    )

    # Mutable state the fake evaluator closes over. Defaults to "fresh"
    # so the first run INSERTs all 4 records as "fresh".
    status_box = {"status": "fresh"}

    def _fake_evaluate(
        timeframe: str, last_received_at: Any, now: Any, **kwargs: Any
    ) -> FreshnessResult:
        return FreshnessResult(
            stream_name=f"market:{timeframe}",
            status=status_box["status"],
            observed_at=now,
            blocks_active_trading=status_box["status"] != "fresh",
            reason="test-fake",
        )

    monkeypatch.setattr(
        "clay.ingestion.service.evaluate_market_freshness",
        _fake_evaluate,
    )

    # --- Run 1: INSERT, status = "fresh" → 4 transitions ---
    status_box["status"] = "fresh"
    summary_1 = await service.run_once(emit=False)
    assert summary_1.freshness_state_transitions == 4
    assert summary_1.freshness_updates_written == 4  # informational

    # --- Run 2: UPDATE same state, status still "fresh" → 0 transitions ---
    summary_2 = await service.run_once(emit=False)
    assert summary_2.freshness_state_transitions == 0, (
        "steady-state UPDATE must NOT increment transition counter "
        "(Поправка 2 anti-flood)"
    )
    assert summary_2.freshness_updates_written == 4  # informational, still counts

    # --- Run 3: UPDATE different state, status flips to "stale" → 4 transitions ---
    status_box["status"] = "stale"
    summary_3 = await service.run_once(emit=False)
    assert summary_3.freshness_state_transitions == 4
    assert summary_3.freshness_updates_written == 4


@pytest.mark.anyio
async def test_market_records_inserted_updated_split_correctly(
    sqlite_session_factory,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
) -> None:
    """Counter split (MED-C): 1st run → all INSERT, 2nd run → all UPDATE.

    ``market_records_written`` stays as a computed property
    (``= inserted + updated``) so the pre-B5 ``assert ... == 4``
    contract is preserved; the new ``market_records_inserted`` and
    ``market_records_updated`` fields expose the split.

    C3: DB verification via separate session.
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    service = _build_service(
        sqlite_session_factory, sqlite_settings, audit_writer, event_bus
    )

    # First run — 4 new bars, all INSERTed.
    summary_1 = await service.run_once(emit=False)
    assert summary_1.market_records_inserted == 4
    assert summary_1.market_records_updated == 0
    assert summary_1.market_records_written == 4  # computed property

    # Second run — same bars, all UPDATEd.
    summary_2 = await service.run_once(emit=False)
    assert summary_2.market_records_inserted == 0
    assert summary_2.market_records_updated == 4
    assert summary_2.market_records_written == 4  # computed property

    # And the pre-B5 contract is preserved — verify via separate session.
    with sqlite_session_factory() as session:
        market_repo = MarketRepository(session)
        assert len(market_repo.list_latest_bars(limit=100)) == 4


@pytest.mark.anyio
async def test_persist_runs_in_worker_thread(
    sqlite_session_factory,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C3 acceptance: sync-DB persist runs in a **worker thread**, not the event loop.

    Spies on ``IngestionCycleService._persist`` to capture the
    thread identity and asserts it differs from the main (test)
    coroutine's thread — proving ``asyncio.to_thread`` offloads
    the DB work.
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    service = _build_service(
        sqlite_session_factory, sqlite_settings, audit_writer, event_bus
    )
    main_thread = threading.get_ident()
    persist_thread: list[object] = [None]

    original = service._persist  # noqa: SLF001

    def spy(collected: _CollectedData, started_at: datetime) -> IngestionRunSummary:
        persist_thread[0] = threading.get_ident()
        return original(collected, started_at)

    monkeypatch.setattr(service, "_persist", spy)

    await service.run_once(emit=False)

    assert persist_thread[0] is not None, "persist was never called"
    assert persist_thread[0] != main_thread, (
        f"_persist ran on the event-loop thread ({main_thread}), "
        f"expected a different (worker) thread"
    )


class _SecondFakeClient:
    """A second fake client for the E3 synthetic 2-exchange seam test."""

    source: str = "bybit_spot"

    async def fetch_klines(  # noqa: PLR6301
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
    ) -> list[NormalizedMarketBar]:
        del symbol, interval, limit
        return [
            NormalizedMarketBar(
                symbol="ETHUSDT",
                timeframe="5m",
                open=3500.0,
                high=3510.0,
                low=3490.0,
                close=3505.0,
                volume=50.0,
                quote_volume=175000.0,
                source="bybit_spot",
                bar_open_time=datetime(2024, 4, 1, 7, 0, tzinfo=UTC),
                bar_close_time=datetime(2024, 4, 1, 7, 14, 59, 999000, tzinfo=UTC),
            ),
        ]

    def set_http_client(self, client: object | None) -> None:
        return


@pytest.mark.anyio
async def test_two_exchange_seam_dispatches_clients_correctly(
    sqlite_session_factory: Any,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
) -> None:
    """E3 synthetic 2-exchange seam test: both exchanges produce bars tagged with own source.

    Proves that the multi-exchange produce path works without a real
    second exchange adapter (e.g. Bybit).  At E3 there is only
    ``binance_spot`` in production, but the same dispatch logic runs.
    """
    # Exchange 1: binance (existing fake, source="test")
    binance_client = _FakeBinanceClient()
    binance_config = ExchangeConfig(
        exchange_id="binance_spot",
        source="binance_spot",
        enabled=True,
        base_url="http://fake",
        symbols=list(sqlite_settings.market_symbols),
        timeframes=list(sqlite_settings.market_timeframes),
    )
    # Exchange 2: bybit (second fake, source="bybit_spot")
    bybit_client = _SecondFakeClient()
    bybit_config = ExchangeConfig(
        exchange_id="bybit_spot",
        source="bybit_spot",
        enabled=True,
        base_url="http://fake",
        symbols=["ETHUSDT"],
        timeframes=["5m"],
    )
    market_service = MarketIngestionService(
        {
            "binance_spot": (binance_client, binance_config),
            "bybit_spot": (bybit_client, bybit_config),
        }
    )
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    service = IngestionCycleService(
        settings=sqlite_settings,
        market_service=market_service,
        context_manager=ContextConnectorManager([]),
        session_factory=sqlite_session_factory,
        audit_writer=audit_writer,
        event_bus=event_bus,
    )

    summary = await service.run_once(emit=False)

    # Both exchanges produced records
    assert summary.market_records_written >= 2  # 1 from bybit + >=1 from binance

    with sqlite_session_factory() as session:
        from sqlalchemy import select
        from clay.db.models_market import MarketBar

        rows = session.scalars(select(MarketBar)).all()
        sources = {r.source for r in rows}
        # At least the second exchange's source appears
        assert "bybit_spot" in sources


@pytest.mark.anyio
async def test_per_exchange_failure_isolation_continues_healthy_exchange(
    sqlite_session_factory: Any,
    sqlite_settings: IngestionSettings,
    tmp_path: Path,
) -> None:
    """E3: one exchange raises → the other exchange persists its bars.

    The failed exchange gets ``freshness_state="unknown"`` while the
    healthy exchange's data flows through normally.
    """

    class _FailingFakeClient:
        source: str = "failing_exchange"

        async def fetch_klines(
            self,
            symbol: str,
            interval: str,
            limit: int = 200,
        ) -> list[NormalizedMarketBar]:
            del symbol, interval, limit
            raise TimeoutError("simulated failure")

        def set_http_client(self, client: object | None) -> None:
            return

    failing_client = _FailingFakeClient()
    failing_config = ExchangeConfig(
        exchange_id="failing",
        source="failing_exchange",
        enabled=True,
        base_url="http://fake",
        symbols=["BTCUSDT"],
        timeframes=["5m"],
    )
    healthy_client = _FakeBinanceClient()
    healthy_config = ExchangeConfig(
        exchange_id="healthy",
        source="healthy",
        enabled=True,
        base_url="http://fake",
        symbols=list(sqlite_settings.market_symbols),
        timeframes=list(sqlite_settings.market_timeframes),
    )
    market_service = MarketIngestionService(
        {
            "failing": (failing_client, failing_config),
            "healthy": (healthy_client, healthy_config),
        }
    )
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    service = IngestionCycleService(
        settings=sqlite_settings,
        market_service=market_service,
        context_manager=ContextConnectorManager([]),
        session_factory=sqlite_session_factory,
        audit_writer=audit_writer,
        event_bus=event_bus,
    )

    summary = await service.run_once(emit=False)

    # Healthy exchange persisted its bars
    assert summary.market_records_written >= 4

    with sqlite_session_factory() as session:
        from sqlalchemy import select
        from clay.db.models_market import MarketBar, MarketFreshnessStatus

        # Healthy bars are persisted
        rows = session.scalars(select(MarketBar)).all()
        assert len(rows) >= 4
        for row in rows:
            assert row.source in ("binance_spot", "healthy")

        # Failing exchange has freshness="unknown"
        freshness_rows = session.scalars(select(MarketFreshnessStatus)).all()
        failing_freshness = [
            r for r in freshness_rows if r.source == "failing_exchange"
        ]
        assert len(failing_freshness) == 1
        assert failing_freshness[0].freshness_state == "unknown"
