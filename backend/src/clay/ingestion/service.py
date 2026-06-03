import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import utils as email_utils
from typing import Any

import httpx
from sqlalchemy.orm import Session, sessionmaker

from clay.audit.writer import AuditWriter
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.events.bus import EventBus
from clay.freshness.evaluator import evaluate_market_freshness
from clay.ingestion.context.manager import ConnectorRunResult, ContextConnectorManager
from clay.ingestion.market.service import MarketIngestionService
from clay.settings.ingestion import IngestionSettings

import logging

logger = logging.getLogger(__name__)


def _resolve_retry_delay(
    exc: Exception,
    *,
    default_delay: float,
    cap: float,
) -> float:
    """Resolve the effective retry delay for an HTTP exception.

    For 429 (rate-limit) and 418 (IP-ban) responses, attempts to
    honour the ``Retry-After`` header (seconds or HTTP-date format),
    capped at ``cap`` seconds.  For all other exceptions / missing
    headers / parse failures, falls back to ``default_delay``.
    """
    if not isinstance(exc, httpx.HTTPStatusError):
        return default_delay
    if exc.response.status_code not in (429, 418):
        return default_delay

    retry_after = exc.response.headers.get("Retry-After")
    if retry_after is None:
        return default_delay

    try:
        parsed = float(retry_after)
    except (ValueError, TypeError):
        try:
            parsed_date = email_utils.parsedate_to_datetime(retry_after)
            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(tzinfo=UTC)
            parsed = (parsed_date - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return default_delay

    return max(0.0, min(parsed, cap))


@dataclass(slots=True)
class IngestionRunSummary:
    started_at: datetime
    finished_at: datetime
    market_records_inserted: int = 0
    market_records_updated: int = 0
    news_records_written: int = 0
    sentiment_records_written: int = 0
    freshness_updates_written: int = 0
    freshness_state_transitions: int = 0
    connector_statuses: list[dict[str, Any]] = field(default_factory=list)
    incidents: list[dict[str, str]] = field(default_factory=list)

    @property
    def market_records_written(self) -> int:
        """B5: backward-compat with the pre-B5 ``assert ... == 4`` contract.

        Pre-B5 the field stored the total; B5 split it into
        ``inserted`` and ``updated`` (MED-C, audit-quality count
        of new vs. updated bars). Existing tests + manual callers
        keep reading ``market_records_written`` and get the same
        total via this computed property.
        """
        return self.market_records_inserted + self.market_records_updated

    def as_payload(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "market_records_written": self.market_records_written,
            "market_records_inserted": self.market_records_inserted,
            "market_records_updated": self.market_records_updated,
            "news_records_written": self.news_records_written,
            "sentiment_records_written": self.sentiment_records_written,
            "freshness_updates_written": self.freshness_updates_written,
            "freshness_state_transitions": self.freshness_state_transitions,
            "connector_statuses": self.connector_statuses,
            "incidents": self.incidents,
        }


@dataclass(slots=True)
class _MarketBatch:
    """DTO for one symbol+timeframe fetch result — plain data, no ORM."""

    symbol: str
    timeframe: str
    bars: list[Any] | None = None
    error: Exception | None = None

    @property
    def is_failure(self) -> bool:
        return self.error is not None


@dataclass(slots=True)
class _CollectedData:
    """Plain DTO that carries async-collected data into the sync ``_persist`` thread.

    All fields are plain Python objects (dataclasses / pydantic models /
    dicts) — **zero** ORM instances, lazy-loaded proxies, or
    session-bound references.
    """

    started_at: datetime
    market_batches: list[_MarketBatch]
    context_results: list[ConnectorRunResult]


class IngestionCycleBusy(RuntimeError):
    """Raised when an ingestion cycle is already in progress.

    The B5 ``asyncio.Lock`` wraps the full ``_do_run_once`` body
    (market + context + commit). A second concurrent caller — be
    it the manual route or the scheduler-job racing the route —
    gets this exception instead of queueing a duplicate cycle.
    """


class IngestionCycleService:
    """B5: lock-guarded, emit-gated ingestion cycle.

    Concurrency:

    * ``self._lock: asyncio.Lock`` is acquired for the entire
      ``_do_run_once`` body. Manual route catches ``IngestionCycleBusy``
      → ``409 Conflict``. Scheduler-job catches it in
      ``IngestionCycleJob.run()`` and skips the tick quietly.
    * ``is_running`` is a fast non-blocking property built on
      ``lock.locked()`` — used by the scheduler-job's pre-tick
      check (the TOCTOU race that gets past it is then caught
      inside ``run_once``).

    Emit semantics:

    * ``run_once(session, *, emit=True)`` — manual route path.
      After the lock releases, ``emit_cycle_events(summary)`` is
      called (audit + bus).
    * ``run_once(session, *, emit=False)`` — scheduler-driven
      path. DB writes (market bars + freshness + ops rows) are
      **always** persisted; the only thing skipped is
      audit + bus (the scheduler-job has its own transition-only
      emit on top of ``IngestionCycleService.emit_cycle_events``).
    * ``emit_cycle_events(summary)`` is a **public** method so
      the B5 ``IngestionCycleJob`` can call it directly on a
      transition (single source of payload shape, anti-drift).
    """

    def __init__(
        self,
        *,
        settings: IngestionSettings,
        market_service: MarketIngestionService,
        context_manager: ContextConnectorManager,
        session_factory: sessionmaker,
        audit_writer: AuditWriter | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.settings = settings
        self.market_service = market_service
        self.context_manager = context_manager
        self._session_factory = session_factory
        self._audit_writer = audit_writer
        self._event_bus = event_bus
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        """True iff the cycle lock is currently held.

        Fast non-blocking check via ``asyncio.Lock.locked()`` —
        used by the scheduler-job's pre-tick guard. The real
        concurrency guarantee still comes from the lock
        acquisition inside ``run_once``.
        """
        return self._lock.locked()

    async def run_once(
        self,
        *,
        emit: bool = True,
    ) -> IngestionRunSummary:
        """Run one ingestion cycle, then optionally emit.

        ``emit=True`` is the manual-route default — audit + bus
        on completion. ``emit=False`` is the scheduler-job path —
        DB writes mandatory, observability skipped (the job has
        its own transition-only emit on top).

        C3: the cycle is split into two phases — async collect
        (httpx fetch on the event loop, DB-free) and sync persist
        (DB writes in a worker thread via ``asyncio.to_thread``).
        The sync phase opens **its own** ``Session`` from the
        injected ``session_factory`` — no caller-provided session
        crosses the thread boundary.
        """
        if self._lock.locked():
            raise IngestionCycleBusy("ingestion cycle already running")
        async with self._lock:
            summary = await self._do_run_once()
        if emit:
            self.emit_cycle_events(summary)
        return summary

    async def _do_run_once(self) -> IngestionRunSummary:
        """C3: split into async collect (on loop) → sync persist (via ``to_thread``).

        Phase 1 — async collect (DB-free, httpx on event loop).
        Phase 2 — sync persist (own session in worker thread).
        The lock is held for both phases (B5 invariant).
        """
        started_at = datetime.now(UTC)
        collected = await self._collect()
        summary = await asyncio.to_thread(
            self._persist, collected, started_at,
        )
        return summary

    def emit_cycle_events(self, summary: IngestionRunSummary) -> None:
        """Public entry point for the ``ingestion.run`` audit + bus events.

        Single source of truth for the payload shape — shared by
        the manual route (``emit=True``) and the B5
        ``IngestionCycleJob`` on a transition. No-op when the
        service was constructed without ``audit_writer`` /
        ``event_bus`` (dev/test wiring) — keeps the service usable
        from pre-B5 tests that do not care about the audit surface.
        """
        if self._audit_writer is None or self._event_bus is None:
            return  # нечего эмитить (test/incomplete wiring)
        payload = summary.as_payload()
        self._audit_writer.write("ingestion.run", payload)
        self._event_bus.publish(
            "ingestion.updated",
            {"event_type": "ingestion.run", **payload},
        )

    async def _collect(self) -> _CollectedData:
        """Phase 1: async data collection — httpx fetches on the event loop, no DB.

        Returns a plain ``_CollectedData`` DTO (zero ORM references)
        that is then passed to ``_persist`` which runs in a
        ``to_thread`` worker thread with **its own** ``Session``.
        """
        market_batches = await self._collect_market_bars()
        context_results = await self.context_manager.run_once()
        return _CollectedData(
            started_at=datetime.now(UTC),
            market_batches=market_batches,
            context_results=context_results,
        )

    async def _collect_market_bars(self) -> list[_MarketBatch]:
        """Async fetch per symbol+timeframe with per-symbol failure isolation.

        🔴 C3 fix: preserves the pre-C3 semantics where a single
        symbol failure does **not** abort the whole cycle — the
        error is captured in ``_MarketBatch.error`` and the loop
        continues to the next symbol. The failure is then persisted
        (health event + freshness status) in the ``_persist`` phase.
        No DB writes happen here — all writes are deferred to the
        sync ``_persist_market_bars`` running in the worker thread.
        """
        if not self.settings.binance_spot_enabled:
            return []

        batches: list[_MarketBatch] = []
        for symbol in self.settings.market_symbols:
            for timeframe in self.settings.market_timeframes:
                try:
                    bars = await self._fetch_market_bars(
                        symbol=symbol, timeframe=timeframe,
                    )
                    batches.append(_MarketBatch(
                        symbol=symbol, timeframe=timeframe, bars=bars,
                    ))
                except Exception as exc:
                    batches.append(_MarketBatch(
                        symbol=symbol, timeframe=timeframe,
                        error=exc,
                    ))
        return batches

    def _persist(
        self,
        collected: _CollectedData,
        started_at: datetime,
    ) -> IngestionRunSummary:
        """Phase 2: sync persist — opens **its own** ``Session`` in the worker thread.

        Creates one ``Session`` from ``self._session_factory``,
        performs all DB writes, commits, and returns a fully
        materialised ``IngestionRunSummary`` to the event loop.
        The summary contains only plain types (ints, timestamps,
        string lists) — zero session-bound ORM references.
        """
        with self._session_factory() as session:
            market_repo = MarketRepository(session)
            context_repo = ContextRepository(session)
            ops_repo = OpsRepository(session)
            summary = IngestionRunSummary(
                started_at=started_at,
                finished_at=started_at,
            )

            self._persist_market_bars(market_repo, ops_repo, summary, collected)
            self._persist_context(context_repo, ops_repo, summary, collected)

            summary.finished_at = datetime.now(UTC)
            session.commit()
            return summary

    def _persist_market_bars(
        self,
        market_repo: MarketRepository,
        ops_repo: OpsRepository,
        summary: IngestionRunSummary,
        collected: _CollectedData,
    ) -> None:
        """Sync persist market bars + freshness + health events."""
        if not self.settings.binance_spot_enabled:
            return

        market_run = ops_repo.create_ingest_run(
            source_name="binance_spot",
            source_type="market",
            status="running",
            started_at=collected.started_at,
            details={
                "symbols": self.settings.market_symbols,
                "timeframes": self.settings.market_timeframes,
            },
        )

        incidents_before = len(summary.incidents)

        for batch in collected.market_batches:
            if batch.is_failure:
                # 🔴 C3 fix: per-symbol failure isolation — record
                # incident + health event + unknown freshness,
                # then continue to the next batch.
                assert batch.error is not None
                observed_at = datetime.now(UTC)
                message = self._format_exception_message(batch.error)
                summary.incidents.append({
                    "source_name": f"binance_spot:{batch.symbol}:{batch.timeframe}",
                    "severity": "error",
                    "message": message,
                })
                ops_repo.record_source_health_event(
                    source_name=f"binance_spot:{batch.symbol}:{batch.timeframe}",
                    severity="error",
                    message=message,
                    recorded_at=observed_at,
                )
                market_repo.upsert_freshness_status(
                    symbol=batch.symbol, timeframe=batch.timeframe,
                    freshness_state="unknown", evaluated_at=observed_at,
                    latest_bar_open_time=None, is_stale=True,
                )
                summary.freshness_updates_written += 1
                continue

            assert batch.bars is not None
            inserted, updated = self.market_service.persist_bars(
                market_repo, batch.bars,
            )
            summary.market_records_inserted += inserted
            summary.market_records_updated += updated

            latest_bar = max(
                batch.bars,
                key=lambda candidate: candidate.bar_close_time,
            )
            freshness = evaluate_market_freshness(
                timeframe=batch.timeframe,
                last_received_at=latest_bar.bar_close_time,
                now=datetime.now(UTC),
            )
            state_changed = market_repo.upsert_freshness_status(
                symbol=batch.symbol, timeframe=batch.timeframe,
                freshness_state=freshness.status,
                evaluated_at=freshness.observed_at,
                latest_bar_open_time=latest_bar.bar_open_time,
                is_stale=freshness.status != "fresh",
            )
            if state_changed:
                summary.freshness_state_transitions += 1
            summary.freshness_updates_written += 1
            ops_repo.resolve_source_health_events(
                source_name=f"binance_spot:{batch.symbol}:{batch.timeframe}",
                resolved_at=freshness.observed_at,
                resolution_message="Market ingest recovered after successful refresh.",
            )

        incidents_after = len(summary.incidents)
        market_status = "success"
        if incidents_after > incidents_before and (
            summary.market_records_inserted + summary.market_records_updated
        ) > 0:
            market_status = "partial_failure"
        elif incidents_after > incidents_before:
            market_status = "failed"

        ops_repo.finalize_ingest_run(
            market_run,
            status=market_status,
            finished_at=datetime.now(UTC),
            details={
                "market_records_written": (
                    summary.market_records_inserted + summary.market_records_updated
                ),
                "freshness_updates_written": summary.freshness_updates_written,
            },
        )

    def _persist_context(
        self,
        context_repo: ContextRepository,
        ops_repo: OpsRepository,
        summary: IngestionRunSummary,
        collected: _CollectedData,
    ) -> None:
        """Sync persist context data (news, sentiment) + connector runs + health."""
        for result in collected.context_results:
            run = ops_repo.create_ingest_run(
                source_name=result.source_name,
                source_type=result.connector_type,
                status="running",
                started_at=result.started_at,
                details={"connector_id": result.connector_id},
            )
            ops_repo.record_connector_status(
                connector_id=result.connector_id,
                connector_type=result.connector_type,
                status=result.status,
                observed_at=result.finished_at,
                details=result.details,
            )

            if result.connector_type == "news":
                summary.news_records_written += context_repo.store_news_items(
                    result.payloads,
                )
            elif result.connector_type == "sentiment":
                summary.sentiment_records_written += (
                    context_repo.store_sentiment_snapshots(result.payloads)
                )

            final_status = result.status
            if result.status == "healthy":
                final_status = "success"
                ops_repo.resolve_source_health_events(
                    source_name=result.source_name,
                    resolved_at=result.finished_at,
                    resolution_message="Connector recovered after healthy run.",
                )
            elif result.status == "disabled":
                final_status = "skipped"
            elif result.status != "success":
                summary.incidents.append(
                    {
                        "source_name": result.source_name,
                        "severity": "warning" if result.status == "degraded" else "error",
                        "message": result.details.get("error", result.status),
                    },
                )
                ops_repo.record_source_health_event(
                    source_name=result.source_name,
                    severity="warning" if result.status == "degraded" else "error",
                    message=str(result.details.get("error", result.status)),
                    recorded_at=result.finished_at,
                )

            ops_repo.finalize_ingest_run(
                run,
                status=final_status,
                finished_at=result.finished_at,
                details={
                    "connector_id": result.connector_id,
                    "payload_count": len(result.payloads),
                    **result.details,
                },
            )
            summary.connector_statuses.append(
                {
                    "connector_id": result.connector_id,
                    "connector_type": result.connector_type,
                    "status": result.status,
                    "payload_count": len(result.payloads),
                },
            )

    async def _fetch_market_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
    ) -> list[Any]:
        last_error: Exception | None = None
        cap = self.settings.binance_retry_after_cap_seconds
        for attempt in range(1, self.settings.market_fetch_max_attempts + 1):
            try:
                return await self.market_service.fetch_and_normalize(
                    symbol=symbol,
                    interval=timeframe,
                )
            except Exception as exc:
                last_error = exc
                if attempt >= self.settings.market_fetch_max_attempts:
                    break
                delay = _resolve_retry_delay(
                    exc,
                    default_delay=self.settings.market_fetch_retry_delay_seconds,
                    cap=cap,
                )
                if delay != self.settings.market_fetch_retry_delay_seconds:
                    logger.warning(
                        "clay.ingestion: %s %s — Retry-After %ss honoured (capped %ss)",
                        symbol, timeframe, delay, cap,
                    )
                await asyncio.sleep(delay)

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"market ingest failed without exception for {symbol}:{timeframe}")

    def _format_exception_message(self, exc: Exception) -> str:
        message = str(exc).strip()
        if message:
            return message
        return type(exc).__name__
