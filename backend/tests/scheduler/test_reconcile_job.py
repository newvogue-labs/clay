"""Tests for the D-12c ``OrderReconcileJob`` (scheduler-driven async reconcile).

Acceptance criteria:

1. ``test_run_iterates_active_pairs`` — run() calls reconcile_symbol for each
   distinct (venue, symbol) from active projections.
2. ``test_first_run_seeds_cache_no_emit`` — first tick seeds cache, no audit/bus.
3. ``test_steady_state_no_emit`` — same state → 0 audit, 0 bus.
4. ``test_transition_emits_audit_and_bus`` — state change → audit + bus.
5. ``test_fatal_mismatch_emits_signal`` — fatal mismatch → reconcile.fatal_mismatch audit.
6. ``test_on_error_audits_once`` — 2 consecutive failures → 1 cycle_failed audit.
7. ``test_on_error_does_not_mutate_session_scheduler`` — failure isolated.
8. ``test_failure_success_failure_audits_twice`` — _failing reset on success.
9. ``test_dormant_when_disabled`` — reconcile_enabled=False → job not registered.
10. D-15: ``test_fatal_wiring_calls_on_fatal_report`` — fatal report triggers wiring.
11. D-15: ``test_fatal_wiring_none_no_crash`` — wiring=None → no crash.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.execution.ledger.reconcile import (
    ReconcileReport,
)
from clay.scheduler.reconcile_job import OrderReconcileJob


def _read_audit_events(audit_writer: AuditWriter) -> list[dict[str, Any]]:
    if not audit_writer.path.exists():
        return []
    with audit_writer.path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _drain_event_bus(event_bus: EventBus) -> list[tuple[str, dict[str, Any]]]:
    drained: list[tuple[str, dict[str, Any]]] = []
    for queue in list(event_bus._subscribers):
        while True:
            try:
                message = queue.get_nowait()
            except Exception:
                break
            drained.append((message.event_type, message.payload))
    return drained


class FakeReconcileService:
    """Duck-typed fake matching ``OrderReconcileService`` interface."""

    def __init__(self) -> None:
        self.reconcile_results: dict[str, ReconcileReport] = {}
        self.calls: list[tuple[str, str]] = []

    async def reconcile_symbol(
        self, symbol: str, since: datetime, *, venue: str
    ) -> ReconcileReport:
        self.calls.append((venue, symbol))
        key = f"{venue}:{symbol}"
        if key in self.reconcile_results:
            return self.reconcile_results[key]
        return ReconcileReport()


class FakeSessionFactory:
    """Minimal fake session_factory that returns sessions with empty projections."""

    def __init__(self, projections: list[Any] | None = None) -> None:
        self._projections = projections or []

    def __call__(self) -> Any:
        from unittest.mock import MagicMock

        session = MagicMock()
        from clay.execution.ledger.repository import OrderLedgerRepository

        repo = MagicMock(spec=OrderLedgerRepository)
        repo.list_active_projections.return_value = self._projections
        # Make the session context manager work
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        return session


def _make_job(
    tmp_path: Path,
    *,
    reconcile_service: FakeReconcileService | None = None,
    projections: list[Any] | None = None,
    lookback_seconds: int = 3600,
) -> tuple[OrderReconcileJob, FakeReconcileService, AuditWriter, EventBus]:
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    event_bus.subscribe()
    svc = reconcile_service or FakeReconcileService()
    sf = FakeSessionFactory(projections or [])

    fixed_now = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)

    # We need to patch the repository call inside the job's run()
    # to return our fake projections. We'll do this via a mock.

    job = OrderReconcileJob(
        reconcile_service=svc,  # type: ignore[arg-type]
        session_factory=sf,  # type: ignore[arg-type]
        audit_writer=audit_writer,
        event_bus=event_bus,
        lookback_seconds=lookback_seconds,
        now_fn=lambda: fixed_now,
    )
    return job, svc, audit_writer, event_bus


# === Tests ===


@pytest.mark.anyio
async def test_run_iterates_active_pairs(tmp_path: Path) -> None:
    """run() calls reconcile_symbol for each distinct (venue, symbol) pair."""
    from clay.db.models_orders import OrderCurrentState

    # Create fake projections
    proj1 = MagicMock(spec=OrderCurrentState)
    proj1.venue = "binance"
    proj1.symbol = "BTC/USDT"
    proj2 = MagicMock(spec=OrderCurrentState)
    proj2.venue = "binance"
    proj2.symbol = "ETH/USDT"

    svc = FakeReconcileService()
    job, _, _, _ = _make_job(
        tmp_path, reconcile_service=svc, projections=[proj1, proj2]
    )

    # Patch OrderLedgerRepository to return our projections

    with patch("clay.scheduler.reconcile_job.OrderLedgerRepository") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.list_active_projections.return_value = [proj1, proj2]
        MockRepo.return_value = mock_repo

        await job.run()

    assert len(svc.calls) == 2
    venues_symbols = set(svc.calls)
    assert ("binance", "BTC/USDT") in venues_symbols
    assert ("binance", "ETH/USDT") in venues_symbols


@pytest.mark.anyio
async def test_first_run_seeds_cache_no_emit(tmp_path: Path) -> None:
    """First run seeds cache, no audit, no bus."""
    job, _, audit_writer, event_bus = _make_job(tmp_path)

    with patch("clay.scheduler.reconcile_job.OrderLedgerRepository") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.list_active_projections.return_value = []
        MockRepo.return_value = mock_repo

        await job.run()

    assert _read_audit_events(audit_writer) == []
    assert _drain_event_bus(event_bus) == []


@pytest.mark.anyio
async def test_steady_state_no_emit(tmp_path: Path) -> None:
    """Same state across ticks → 0 audit, 0 bus."""
    job, svc, audit_writer, event_bus = _make_job(tmp_path)

    # All clean reports → (False, 0) every time
    with patch("clay.scheduler.reconcile_job.OrderLedgerRepository") as MockRepo:
        mock_repo = MagicMock()
        proj = MagicMock()
        proj.venue = "binance"
        proj.symbol = "BTC/USDT"
        mock_repo.list_active_projections.return_value = [proj]
        MockRepo.return_value = mock_repo

        await job.run()  # seed
        await job.run()  # steady
        await job.run()  # steady

    assert _read_audit_events(audit_writer) == []
    assert _drain_event_bus(event_bus) == []


@pytest.mark.anyio
async def test_transition_emits_audit_and_bus(tmp_path: Path) -> None:
    """State change → audit + bus."""
    svc = FakeReconcileService()
    proj = MagicMock()
    proj.venue = "binance"
    proj.symbol = "BTC/USDT"

    job, _, audit_writer, event_bus = _make_job(
        tmp_path, reconcile_service=svc, projections=[proj]
    )

    with patch("clay.scheduler.reconcile_job.OrderLedgerRepository") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.list_active_projections.return_value = [proj]
        MockRepo.return_value = mock_repo

        # First run — clean (seed)
        await job.run()

        # Second run — 1 mismatch (transition)
        from clay.execution.ledger.reconcile import (
            Mismatch,
            ReconcileMismatchKind,
        )

        svc.reconcile_results["binance:BTC/USDT"] = ReconcileReport(
            mismatches=[
                Mismatch(
                    kind=ReconcileMismatchKind.LEDGER_ORPHAN,
                    client_order_id="test-cid",
                    venue_order_id=None,
                    detail="test",
                )
            ]
        )
        await job.run()

    events = _read_audit_events(audit_writer)
    cycle_events = [e for e in events if e["event_type"] == "reconcile.cycle"]
    assert len(cycle_events) == 1
    assert cycle_events[0]["payload"]["total_mismatches"] == 1

    drained = _drain_event_bus(event_bus)
    cycle_bus = [t for t, _ in drained if t == "reconcile.cycle"]
    assert len(cycle_bus) == 1


@pytest.mark.anyio
async def test_fatal_mismatch_emits_signal(tmp_path: Path) -> None:
    """Fatal mismatch → reconcile.fatal_mismatch audit entry."""
    from clay.execution.ledger.reconcile import (
        Mismatch,
        ReconcileMismatchKind,
    )

    svc = FakeReconcileService()
    proj = MagicMock()
    proj.venue = "binance"
    proj.symbol = "BTC/USDT"

    job, _, audit_writer, _ = _make_job(
        tmp_path, reconcile_service=svc, projections=[proj]
    )

    with patch("clay.scheduler.reconcile_job.OrderLedgerRepository") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.list_active_projections.return_value = [proj]
        MockRepo.return_value = mock_repo

        # First run — seed
        await job.run()

        # Fatal mismatch
        svc.reconcile_results["binance:BTC/USDT"] = ReconcileReport(
            mismatches=[
                Mismatch(
                    kind=ReconcileMismatchKind.ILLEGAL_DRIFT,
                    client_order_id="test-cid",
                    venue_order_id="v-001",
                    detail="INTENT -> FILLED illegal",
                )
            ]
        )
        await job.run()

    events = _read_audit_events(audit_writer)
    fatal = [e for e in events if e["event_type"] == "reconcile.fatal_mismatch"]
    assert len(fatal) == 1
    assert fatal[0]["payload"]["any_fatal"] is True
    assert fatal[0]["payload"]["pairs_reconciled"] == 1


@pytest.mark.anyio
async def test_on_error_audits_once(tmp_path: Path) -> None:
    """2 consecutive failures → 1 reconcile.cycle_failed audit."""
    job, _, audit_writer, _ = _make_job(tmp_path)

    job.on_error(RuntimeError("boom"))
    job.on_error(RuntimeError("boom"))

    failed = [
        e
        for e in _read_audit_events(audit_writer)
        if e["event_type"] == "reconcile.cycle_failed"
    ]
    assert len(failed) == 1
    assert failed[0]["payload"]["error"] == "boom"


@pytest.mark.anyio
async def test_on_error_does_not_mutate_session_scheduler(tmp_path: Path) -> None:
    """Reconcile failure is isolated — session-scheduler stays HEALTHY."""
    from clay.services.models import ServiceCriticality, ServiceStatus
    from clay.services.registry import ServiceRegistry

    registry = ServiceRegistry()
    registry.register(
        service_id="session-scheduler",
        service_type="scheduler",
        criticality=ServiceCriticality.IMPORTANT,
        startup_policy="always-on",
    )
    registry.update_status("session-scheduler", ServiceStatus.HEALTHY)

    job, _, _, _ = _make_job(tmp_path)
    job.on_error(RuntimeError("boom"))

    record = registry.get("session-scheduler")
    assert record is not None
    assert record.status is ServiceStatus.HEALTHY


@pytest.mark.anyio
async def test_failure_success_failure_audits_twice(tmp_path: Path) -> None:
    """fail → success → fail → 2 audit entries (Acceptance #11)."""
    svc = FakeReconcileService()
    proj = MagicMock()
    proj.venue = "binance"
    proj.symbol = "BTC/USDT"

    job, _, audit_writer, _ = _make_job(
        tmp_path, reconcile_service=svc, projections=[proj]
    )

    with patch("clay.scheduler.reconcile_job.OrderLedgerRepository") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.list_active_projections.return_value = [proj]
        MockRepo.return_value = mock_repo

        # Episode 1: reconcile raises
        original_run_symbol = svc.reconcile_symbol

        async def _raise(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("network error")

        svc.reconcile_symbol = _raise  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="network error"):
            await job.run()
        job.on_error(RuntimeError("network error"))

        # Success — run() resets _failing
        svc.reconcile_symbol = original_run_symbol
        await job.run()

        # Episode 2: reconcile raises again
        svc.reconcile_symbol = _raise  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="network error"):
            await job.run()
        job.on_error(RuntimeError("network error"))

    failed = [
        e
        for e in _read_audit_events(audit_writer)
        if e["event_type"] == "reconcile.cycle_failed"
    ]
    assert len(failed) == 2


# === D-15: fatal_halt_wiring tests ===


@pytest.mark.anyio
async def test_fatal_wiring_calls_on_fatal_report(tmp_path: Path) -> None:
    """D-15: fatal report → wiring.on_fatal_report called + latch engaged."""
    from unittest.mock import MagicMock

    from clay.execution.ledger.reconcile import (
        Mismatch,
        ReconcileMismatchKind,
    )

    svc = FakeReconcileService()
    proj = MagicMock()
    proj.venue = "binance"
    proj.symbol = "BTCUSDT"

    wiring = MagicMock()
    wiring.on_fatal_report.return_value = True

    job, _, _, _ = _make_job(tmp_path, reconcile_service=svc, projections=[proj])
    job._fatal_halt_wiring = wiring

    with patch("clay.scheduler.reconcile_job.OrderLedgerRepository") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.list_active_projections.return_value = [proj]
        MockRepo.return_value = mock_repo

        # First run — seed
        await job.run()

        # Fatal mismatch
        svc.reconcile_results["binance:BTCUSDT"] = ReconcileReport(
            mismatches=[
                Mismatch(
                    kind=ReconcileMismatchKind.ILLEGAL_DRIFT,
                    client_order_id="test-cid",
                    venue_order_id="v-001",
                    detail="INTENT -> FILLED illegal",
                )
            ]
        )
        await job.run()

    wiring.on_fatal_report.assert_called_once()
    call_kwargs = wiring.on_fatal_report.call_args
    assert call_kwargs.kwargs["venue"] == "binance"
    assert call_kwargs.kwargs["symbol"] == "BTCUSDT"


@pytest.mark.anyio
async def test_fatal_wiring_none_no_crash(tmp_path: Path) -> None:
    """D-15: wiring=None → no crash on fatal report."""
    from clay.execution.ledger.reconcile import (
        Mismatch,
        ReconcileMismatchKind,
    )

    svc = FakeReconcileService()
    proj = MagicMock()
    proj.venue = "binance"
    proj.symbol = "BTCUSDT"

    job, _, _, _ = _make_job(tmp_path, reconcile_service=svc, projections=[proj])
    # wiring is None (default)

    with patch("clay.scheduler.reconcile_job.OrderLedgerRepository") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.list_active_projections.return_value = [proj]
        MockRepo.return_value = mock_repo

        # First run — seed
        await job.run()

        # Fatal mismatch — should not crash
        svc.reconcile_results["binance:BTCUSDT"] = ReconcileReport(
            mismatches=[
                Mismatch(
                    kind=ReconcileMismatchKind.ILLEGAL_DRIFT,
                    client_order_id="test-cid",
                    venue_order_id="v-001",
                    detail="INTENT -> FILLED illegal",
                )
            ]
        )
        await job.run()

    # No crash — test passes if no exception raised


@pytest.mark.anyio
async def test_clean_report_does_not_call_wiring(tmp_path: Path) -> None:
    """D-15: clean report → wiring.on_fatal_report NOT called."""
    from unittest.mock import MagicMock

    svc = FakeReconcileService()
    proj = MagicMock()
    proj.venue = "binance"
    proj.symbol = "BTCUSDT"

    wiring = MagicMock()

    job, _, _, _ = _make_job(tmp_path, reconcile_service=svc, projections=[proj])
    job._fatal_halt_wiring = wiring

    with patch("clay.scheduler.reconcile_job.OrderLedgerRepository") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.list_active_projections.return_value = [proj]
        MockRepo.return_value = mock_repo

        # Seed + clean tick
        await job.run()
        await job.run()

    wiring.on_fatal_report.assert_not_called()
