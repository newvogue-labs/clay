import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from clay.audit.writer import AuditWriter
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.events.bus import EventBus
from clay.freshness.evaluator import evaluate_market_freshness
from clay.ingestion.context.manager import ContextConnectorManager
from clay.ingestion.market.service import MarketIngestionService
from clay.settings.ingestion import IngestionSettings


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
        audit_writer: AuditWriter | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.settings = settings
        self.market_service = market_service
        self.context_manager = context_manager
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
        session: Session,
        *,
        emit: bool = True,
    ) -> IngestionRunSummary:
        """Run one ingestion cycle (market + context + commit), then optionally emit.

        ``emit=True`` is the manual-route default — audit + bus
        on completion. ``emit=False`` is the scheduler-job path —
        DB writes mandatory, observability skipped (the job has
        its own transition-only emit on top).
        """
        if self._lock.locked():
            # TOCTOU mitigation: explicit guard, not just ``async with``.
            # The scheduler-job already short-circuits on
            # ``is_running``, so this branch is primarily for the
            # manual route racing itself.
            raise IngestionCycleBusy("ingestion cycle already running")
        async with self._lock:
            summary = await self._do_run_once(session)
        # Emit happens **after** the lock release so observability
        # is not serialized with the (potentially slow) cycle body.
        if emit:
            self.emit_cycle_events(summary)
        return summary

    async def _do_run_once(self, session: Session) -> IngestionRunSummary:
        """The actual cycle — market + context + commit, all under the lock."""
        started_at = datetime.now(UTC)
        summary = IngestionRunSummary(
            started_at=started_at,
            finished_at=started_at,
        )

        market_repo = MarketRepository(session)
        context_repo = ContextRepository(session)
        ops_repo = OpsRepository(session)

        await self._run_market_ingest(
            market_repo=market_repo,
            ops_repo=ops_repo,
            summary=summary,
        )
        await self._run_context_ingest(
            context_repo=context_repo,
            ops_repo=ops_repo,
            summary=summary,
        )

        summary.finished_at = datetime.now(UTC)
        session.commit()
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

    async def _run_market_ingest(
        self,
        *,
        market_repo: MarketRepository,
        ops_repo: OpsRepository,
        summary: IngestionRunSummary,
    ) -> None:
        if not self.settings.binance_spot_enabled:
            return

        started_at = datetime.now(UTC)
        market_run = ops_repo.create_ingest_run(
            source_name="binance_spot",
            source_type="market",
            status="running",
            started_at=started_at,
            details={
                "symbols": self.settings.market_symbols,
                "timeframes": self.settings.market_timeframes,
            },
        )

        incidents_before = len(summary.incidents)

        for symbol in self.settings.market_symbols:
            for timeframe in self.settings.market_timeframes:
                try:
                    bars = await self._fetch_market_bars(
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                    inserted, updated = self.market_service.persist_bars(
                        market_repo, bars,
                    )
                    summary.market_records_inserted += inserted
                    summary.market_records_updated += updated

                    latest_bar = max(
                        bars,
                        key=lambda candidate: candidate.bar_close_time,
                    )
                    freshness = evaluate_market_freshness(
                        timeframe=timeframe,
                        last_received_at=latest_bar.bar_close_time,
                        now=datetime.now(UTC),
                    )
                    # B5 Поправка 2: the bool return is the
                    # transition signal. ``freshness_state_transitions``
                    # only grows on a real state change, so a
                    # steady-state tick (same state, only timestamps
                    # updated) leaves the counter at zero — the
                    # ``IngestionCycleJob``'s anti-flood diff then
                    # emits nothing.
                    state_changed = market_repo.upsert_freshness_status(
                        symbol=symbol,
                        timeframe=timeframe,
                        freshness_state=freshness.status,
                        evaluated_at=freshness.observed_at,
                        latest_bar_open_time=latest_bar.bar_open_time,
                        is_stale=freshness.status != "fresh",
                    )
                    if state_changed:
                        summary.freshness_state_transitions += 1
                    summary.freshness_updates_written += 1
                    ops_repo.resolve_source_health_events(
                        source_name=f"binance_spot:{symbol}:{timeframe}",
                        resolved_at=freshness.observed_at,
                        resolution_message="Market ingest recovered after successful refresh.",
                    )
                except Exception as exc:  # pragma: no cover - runtime/network safety
                    observed_at = datetime.now(UTC)
                    message = self._format_exception_message(exc)
                    summary.incidents.append(
                        {
                            "source_name": f"binance_spot:{symbol}:{timeframe}",
                            "severity": "error",
                            "message": message,
                        },
                    )
                    ops_repo.record_source_health_event(
                        source_name=f"binance_spot:{symbol}:{timeframe}",
                        severity="error",
                        message=message,
                        recorded_at=observed_at,
                    )
                    market_repo.upsert_freshness_status(
                        symbol=symbol,
                        timeframe=timeframe,
                        freshness_state="unknown",
                        evaluated_at=observed_at,
                        latest_bar_open_time=None,
                        is_stale=True,
                    )
                    summary.freshness_updates_written += 1

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

    async def _run_context_ingest(
        self,
        *,
        context_repo: ContextRepository,
        ops_repo: OpsRepository,
        summary: IngestionRunSummary,
    ) -> None:
        results = await self.context_manager.run_once()

        for result in results:
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
                summary.sentiment_records_written += context_repo.store_sentiment_snapshots(
                    result.payloads,
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
                await asyncio.sleep(self.settings.market_fetch_retry_delay_seconds)

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"market ingest failed without exception for {symbol}:{timeframe}")

    def _format_exception_message(self, exc: Exception) -> str:
        message = str(exc).strip()
        if message:
            return message
        return type(exc).__name__
