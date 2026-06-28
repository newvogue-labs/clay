"""B6 integration tests — lifespan + scheduler (lifecycle + jobs + audit + bus).

Builds the full service graph via ``build_services_for_integration(tmp_path)``
(real factory + real ``ClayScheduler`` + real jobs, file-based SQLite in
``tmp_path``, isolated ``AuditWriter`` in ``tmp_path/state``), monkeypatches
the ``clay.api.lifespan`` module-level deps to point at the isolated
services (because ``lifespan`` resolves them as module-level imports from
``clay.bootstrap``, and FastAPI ``dependency_overrides`` does NOT intercept
module-level names), and drives the FastAPI app through
``asgi_lifespan.LifespanManager``.

Covers 13 scenarios from the B6 task-packet (Standard+5, plus the
routing-matrix test that confirms Emma's B5 fragment D fix on the
integration level). The existing two tests in ``tests/api/test_lifespan.py``
stay on the production app — they verify module-level wiring against the
real ``clay.bootstrap`` singletons, which is itself a useful smoke test.
This file uses real scheduler + real jobs + isolated DB + isolated audit.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import Any

import pytest
from apscheduler.schedulers.base import STATE_RUNNING
from asgi_lifespan import LifespanManager

import clay.api.lifespan as lifespan_module
from clay.api.main import create_app
from clay.scheduler.service import ClayScheduler
from clay.services.models import ServiceStatus
from clay.settings.scheduler import SchedulerSettings

from ._helpers import build_services_for_integration


# Job ids from scheduler/service.py:107-112
HEALTH_TICK = "health-tick"
RELIABILITY_RECHECK = "reliability-recheck"
OPS_RETENTION = "ops-retention"
INGESTION_CYCLE = "ingestion-cycle"
ALL_JOB_IDS = (HEALTH_TICK, RELIABILITY_RECHECK, OPS_RETENTION, INGESTION_CYCLE)


# --- helpers ---


def _read_audit_events(audit_path: Path) -> list[dict[str, Any]]:
    """Read the JSONL audit log and return parsed events (test helper)."""
    if not audit_path.exists():
        return []
    with audit_path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _events_by_type(
    events: list[dict[str, Any]], event_type: str
) -> list[dict[str, Any]]:
    return [e for e in events if e.get("event_type") == event_type]


# --- fixtures ---


@pytest.fixture
def isolated_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Build isolated services + app, monkeypatch lifespan module-level deps.

    Returns ``(app, services)`` tuple; tests drive the app via
    ``LifespanManager`` and inspect ``services["registry"]`` /
    ``services["audit_writer"]`` / ``services["event_bus"]`` etc.
    directly. ``monkeypatch`` cleans up lifespan module bindings on
    teardown so tests don't leak state.
    """
    services = build_services_for_integration(tmp_path)
    app = create_app()

    # Redirect every ``lifespan`` module-level dep to the isolated service.
    # Lifespan reads these names at runtime (not import time) — so the
    # monkeypatch on the module attribute wins.
    monkeypatch.setattr(lifespan_module, "_audit_writer", services["audit_writer"])
    monkeypatch.setattr(lifespan_module, "_event_bus", services["event_bus"])
    monkeypatch.setattr(lifespan_module, "_health_monitor", services["health_monitor"])
    monkeypatch.setattr(
        lifespan_module, "_ingestion_cycle_service", services["ingestion_cycle_service"]
    )
    monkeypatch.setattr(
        lifespan_module,
        "_market_ingestion_service",
        services["market_ingestion_service"],
    )
    monkeypatch.setattr(lifespan_module, "_registry", services["registry"])
    monkeypatch.setattr(
        lifespan_module, "_reliability_service", services["reliability_service"]
    )
    monkeypatch.setattr(
        lifespan_module, "_session_factory", services["session_factory"]
    )
    monkeypatch.setattr(
        lifespan_module, "scheduler_settings", services["scheduler_settings"]
    )

    return app, services


# --- #1: jobs registered ---


@pytest.mark.anyio
async def test_jobs_registered_all_three(isolated_app) -> None:
    """All 3 jobs (health-tick, reliability-recheck, ingestion-cycle) registered."""
    app, _ = isolated_app
    async with LifespanManager(app):
        apscheduler = app.state.scheduler._apscheduler
        for job_id in ALL_JOB_IDS:
            assert apscheduler.get_job(job_id) is not None, f"{job_id} not registered"


# --- #2: session-scheduler state walk ---


@pytest.mark.anyio
async def test_session_scheduler_state_walk_stopped_healthy_stopped(
    isolated_app,
) -> None:
    """``session-scheduler`` walks ``STOPPED → HEALTHY → STOPPED`` in lockstep
    with the FastAPI lifespan (B3a real-status contract)."""
    app, services = isolated_app
    registry = services["registry"]
    assert registry.get("session-scheduler").status == ServiceStatus.STOPPED

    async with LifespanManager(app):
        assert registry.get("session-scheduler").status == ServiceStatus.HEALTHY
        assert app.state.scheduler is not None

    # After shutdown — back to STOPPED
    assert registry.get("session-scheduler").status == ServiceStatus.STOPPED


# --- #10/#11: APScheduler STATE_RUNNING inside lifespan ---


@pytest.mark.anyio
async def test_apscheduler_state_running_inside_lifespan(isolated_app) -> None:
    """APScheduler is STATE_RUNNING inside the lifespan, after start() ran."""
    app, _ = isolated_app
    async with LifespanManager(app):
        apscheduler = app.state.scheduler._apscheduler
        assert apscheduler.state == STATE_RUNNING


# --- routing matrix (B5 fragment D fix, integration-level confirmation) ---


@pytest.mark.anyio
async def test_routing_matrix_sync_vs_async(isolated_app) -> None:
    """§3 routing on the live scheduler:

    * ``health-tick`` + ``reliability-recheck`` → registered with the
      **sync** ``ClayScheduler._run_safely`` wrapper → ThreadPoolExecutor
      (``executor="default"``).
    * ``ingestion-cycle`` → registered with the **async**
      ``ClayScheduler._arun_safely`` wrapper → ``AsyncIOScheduler``'s
      own event loop (``executor=None``, the default).

    This is the integration-level confirmation of Emma's B5 fragment D
    mandatory code fix — a sync wrapper around an ``async def`` would
    silently never await the coroutine, leaving ingestion dead.
    """
    app, _ = isolated_app
    async with LifespanManager(app):
        apscheduler = app.state.scheduler._apscheduler
        for job_id in (HEALTH_TICK, RELIABILITY_RECHECK):
            job = apscheduler.get_job(job_id)
            assert job is not None
            assert not inspect.iscoroutinefunction(job.func), (
                f"{job_id} must be registered with sync wrapper, got {job.func!r}"
            )
        ingestion_job = apscheduler.get_job(INGESTION_CYCLE)
        assert ingestion_job is not None
        assert inspect.iscoroutinefunction(ingestion_job.func), (
            f"{INGESTION_CYCLE} must be registered with async wrapper, "
            f"got {ingestion_job.func!r}"
        )


# --- #3: scheduler.started audit event ---


@pytest.mark.anyio
async def test_scheduler_started_audit_event(isolated_app) -> None:
    """``scheduler.started`` audit event is written with all 4 jobs in payload."""
    app, services = isolated_app
    audit_path = services["audit_writer"].path
    async with LifespanManager(app):
        pass
    events = _read_audit_events(audit_path)
    started = _events_by_type(events, "scheduler.started")
    assert len(started) == 1
    assert sorted(started[0]["payload"]["jobs"]) == sorted(ALL_JOB_IDS)
    assert started[0]["payload"]["version"] == "3.11.2"


# --- #4: scheduler.stopped audit event ---


@pytest.mark.anyio
async def test_scheduler_stopped_audit_event(isolated_app) -> None:
    """``scheduler.stopped`` audit event is written on shutdown."""
    app, services = isolated_app
    audit_path = services["audit_writer"].path
    async with LifespanManager(app):
        pass
    events = _read_audit_events(audit_path)
    stopped = _events_by_type(events, "scheduler.stopped")
    assert len(stopped) == 1
    assert stopped[0]["payload"] == {"wait": True, "jobs_cleared": 0}


# --- #6: reliability_enabled=False ---


@pytest.mark.anyio
async def test_reliability_disabled_skips_job_keeps_scheduler(
    isolated_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``reliability_enabled=False`` → ``reliability-recheck`` job NOT
    registered; ``health-tick`` and ``ingestion-cycle`` still registered;
    scheduler instance is alive. ``scheduler.started.jobs`` payload
    reflects **truth**, not intent (Q2 single source of truth)."""
    app, services = isolated_app
    settings = SchedulerSettings(enabled=True, reliability_enabled=False)
    monkeypatch.setattr(lifespan_module, "scheduler_settings", settings)

    async with LifespanManager(app):
        apscheduler = app.state.scheduler._apscheduler
        assert apscheduler.get_job(HEALTH_TICK) is not None
        assert apscheduler.get_job(RELIABILITY_RECHECK) is None
        assert apscheduler.get_job(INGESTION_CYCLE) is not None

    events = _read_audit_events(services["audit_writer"].path)
    started = _events_by_type(events, "scheduler.started")
    assert len(started) == 1
    assert sorted(started[0]["payload"]["jobs"]) == sorted(
        [HEALTH_TICK, OPS_RETENTION, INGESTION_CYCLE]
    )


# --- #7: ingestion_enabled=False ---


@pytest.mark.anyio
async def test_ingestion_disabled_skips_job_keeps_scheduler(
    isolated_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``ingestion_enabled=False`` → ``ingestion-cycle`` job NOT registered;
    ``health-tick`` and ``reliability-recheck`` still registered."""
    app, services = isolated_app
    settings = SchedulerSettings(enabled=True, ingestion_enabled=False)
    monkeypatch.setattr(lifespan_module, "scheduler_settings", settings)

    async with LifespanManager(app):
        apscheduler = app.state.scheduler._apscheduler
        assert apscheduler.get_job(HEALTH_TICK) is not None
        assert apscheduler.get_job(RELIABILITY_RECHECK) is not None
        assert apscheduler.get_job(INGESTION_CYCLE) is None

    events = _read_audit_events(services["audit_writer"].path)
    started = _events_by_type(events, "scheduler.started")
    assert len(started) == 1
    assert sorted(started[0]["payload"]["jobs"]) == sorted(
        [HEALTH_TICK, RELIABILITY_RECHECK, OPS_RETENTION]
    )


# --- #8: app.state reset on shutdown ---


@pytest.mark.anyio
async def test_app_state_reset_on_shutdown(isolated_app) -> None:
    """``app.state.scheduler`` and ``app.state.started_at`` reset to ``None``
    after ``LifespanManager.__aexit__`` (the ``finally:`` block in
    ``lifespan.py:106-110``)."""
    app, _ = isolated_app
    async with LifespanManager(app):
        assert app.state.scheduler is not None
        assert app.state.started_at is not None
    # After exit
    assert app.state.scheduler is None
    assert app.state.started_at is None


# --- #9: double-startup pin (B3a soft debt) ---


@pytest.mark.anyio
async def test_double_startup_does_not_crash(isolated_app) -> None:
    """Pin B3a soft debt #10: ``ClayScheduler.start()`` can be called twice
    in close succession without crashing the lifespan (current behaviour
    is a duplicate ``scheduler.started`` audit; this test fixes the
    contract so a future fix doesn't regress the test)."""
    app, services = isolated_app
    audit_path = services["audit_writer"].path
    async with LifespanManager(app):
        scheduler = app.state.scheduler
        # Second call: tolerate the documented B3a soft debt (either
        # duplicate-audit or a raise). What MUST hold: scheduler
        # instance is still a ``ClayScheduler`` and at least one
        # ``scheduler.started`` event was written.
        try:
            scheduler.start()
        except Exception:
            pass

    assert isinstance(scheduler, ClayScheduler)
    events = _read_audit_events(audit_path)
    started = _events_by_type(events, "scheduler.started")
    assert len(started) >= 1


# --- #14: real-tick smoke ---


@pytest.mark.anyio
async def test_health_tick_real_smoke(
    isolated_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real-tick smoke: ``health_tick_interval_seconds=1``, subscribe to
    the ``EventBus`` before the first tick, wait ~2.5s, verify
    ``health.tick`` messages were published.

    This is the only ``ClayScheduler``-level test that exercises a
    real (non-mocked) APScheduler tick — every other test in this file
    is a pure-lifecycle / registration / audit assertion. Per B6 scope
    we limit this to the B3b health-tick; the B4/B5 jobs' transition
    logic is unit-tested in their own test files."""
    app, services = isolated_app
    settings = SchedulerSettings(
        enabled=True,
        health_tick_interval_seconds=1,
        health_stale_after_seconds=2,  # B2 invariant: >= 2 * tick
    )
    monkeypatch.setattr(lifespan_module, "scheduler_settings", settings)

    queue = services["event_bus"].subscribe()
    try:
        async with LifespanManager(app):
            # Wait ~2.5s so APScheduler fires at least one tick at t=1s
            # and possibly a second at t=2s.
            await asyncio.sleep(2.5)

        # Drain queue
        captured: list[tuple[str, dict[str, Any]]] = []
        while True:
            try:
                msg = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            captured.append((msg.event_type, msg.payload))
    finally:
        services["event_bus"].unsubscribe(queue)

    health_tick_events = [e for e in captured if e[0] == "health.tick"]
    assert len(health_tick_events) >= 1, (
        f"expected ≥1 health.tick on event_bus, got {len(health_tick_events)}; "
        f"all captured: {captured[:5]}"
    )


# --- #12: startup-failure partial-failure anti-test ---


@pytest.mark.anyio
async def test_startup_failure_keeps_state_clean(
    isolated_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Partial-failure anti-test (B6 §9 #12). If a step inside
    ``ClayScheduler.start()`` raises, the ``LifespanManager`` re-raises,
    ``app.state.scheduler`` stays ``None`` (confirm (a) invariant:
    ``scheduler.start()`` runs BEFORE ``app.state.scheduler = scheduler``
    in ``lifespan.py:96-97``), and ``scheduler.started`` is **not**
    written to the audit log (the write happens after the failing
    step on ``scheduler/service.py:184``)."""
    app, services = isolated_app
    audit_path = services["audit_writer"].path

    # Inject failure on the first ``add_health_tick_job`` call inside
    # ``ClayScheduler.start()`` — runs after ``apscheduler.start()``
    # but before the audit write on line 184.
    def failing_add_health_tick(self) -> None:
        raise RuntimeError("injected startup failure (B6 #12)")

    monkeypatch.setattr(ClayScheduler, "add_health_tick_job", failing_add_health_tick)

    with pytest.raises(RuntimeError, match="injected startup failure"):
        async with LifespanManager(app):
            pass  # body never reached — startup raised

    # confirm (a) invariant: app.state.scheduler is None (from the
    # guard on ``lifespan.py:80``; line 97 never executes because
    # ``scheduler.start()`` raised on line 96).
    assert app.state.scheduler is None

    # ``scheduler.started`` was NOT written (audit on line 184 is
    # unreachable after the raise on line 171).
    if audit_path.exists():
        events = _read_audit_events(audit_path)
        started = _events_by_type(events, "scheduler.started")
        assert len(started) == 0, f"expected no scheduler.started audit, got {started}"


# --- #13: shutdown-failure partial-failure anti-test ---


@pytest.mark.anyio
async def test_shutdown_failure_pins_state(
    isolated_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Partial-failure anti-test (B6 §9 #13). When
    ``apscheduler.shutdown(wait=...)`` raises (e.g. APScheduler is in
    a broken state, transport layer fails), the exception propagates
    through ``ClayScheduler.shutdown()`` → the ``finally:`` block in
    ``lifespan.py:106-110`` → the ``LifespanManager`` ``__aexit__``.

    Current behaviour pinned by this test:

    * ``scheduler.stopped`` audit is **NOT** written — the write is
      on ``scheduler/service.py:479-482``, AFTER the failing
      ``apscheduler.shutdown`` call on line 477.
    * ``app.state.scheduler`` remains pointing at the
      ``ClayScheduler`` instance — the reset on ``lifespan.py:110``
      is unreachable because the raise aborts the ``finally:`` block.
      This is a minor reference-leak quirk (operator sees the
      scheduler as still "live" on app.state, but the underlying
      ``apscheduler`` is not actually running). Fix candidate for
      a future slice — out of scope for B6.
    """
    app, services = isolated_app
    audit_path = services["audit_writer"].path

    with pytest.raises(RuntimeError, match="injected shutdown failure"):
        async with LifespanManager(app):
            scheduler = app.state.scheduler
            apscheduler = scheduler._apscheduler

            def failing_shutdown(wait: bool = True) -> None:
                raise RuntimeError("injected shutdown failure (B6 #13)")

            apscheduler.shutdown = failing_shutdown  # type: ignore[method-assign]
            # On ``__aexit__``: ``ClayScheduler.shutdown(wait=True)`` →
            # ``apscheduler.shutdown(wait=True)`` → raises. Exception
            # propagates out of the ``async with`` and is caught by
            # ``pytest.raises``.

    # After the raise propagated: ``app.state.scheduler`` was set on
    # startup (``lifespan.py:97``); the ``finally:`` reset on line 110
    # did not run. Pinned quirk — see docstring.
    assert app.state.scheduler is not None

    events = _read_audit_events(audit_path)
    stopped = _events_by_type(events, "scheduler.stopped")
    assert len(stopped) == 0, (
        f"expected no scheduler.stopped audit on shutdown failure, got {stopped}"
    )


# --- C2: lifespan-owned httpx.AsyncClient lifecycle (HIGH-2 + MED-3) ---


@pytest.mark.anyio
async def test_http_client_is_open_during_lifespan_and_closed_after(
    isolated_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C2: the shared ``httpx.AsyncClient`` injected in lifespan is open
    while the app is running and closed after ``LifespanManager`` exits.

    Per Emma's mandatory fix (🟡): pin via ``is_closed`` (deterministic)
    rather than relying on noisy mid-tick assertions. The isolated
    ``market_ingestion_service`` from the fixture is the same object the
    lifespan injects the client into (via
    ``_market_ingestion_service.set_http_client(http_client)``), so
    we read the state directly from the singleton without extra wiring.
    """
    app, services = isolated_app
    market_service = services["market_ingestion_service"]
    # E3: the single (only) exchange client lives in exchange_clients
    first_client = list(market_service.exchange_clients.values())[0][0]

    # The fixture has already rebound lifespan_module._market_ingestion_service
    # to the isolated service — so lifespan calls set_http_client on it.
    # Before startup: no client injected.
    assert first_client._client is None, "client should not be set before startup"

    async with LifespanManager(app):
        # Inside lifespan: client is open and reachable through the singleton.
        assert first_client._client is not None, "set_http_client never called"
        assert first_client._client.is_closed is False, (
            "client should be open during lifespan"
        )

    # After lifespan exit: client is closed (MED-3 — closed strictly after
    # scheduler.shutdown(wait=True) return, so no in-flight job races).
    assert first_client._client.is_closed is True, (
        "client must be closed after shutdown"
    )
