"""FastAPI lifespan context for Clay.

Boot-order contract (carry-forward from A6 + B0 recon + B1 + B3a):

1. **Module import time** (before lifespan runs). ``clay.bootstrap``
   executes ``build_services(config_loader, session_factory)`` on
   import. When ``session_factory`` is provided (production), that
   call also runs ``session_control_service.reconcile_runtime_state()``
   which projects the restored ``_active_session`` back onto
   ``runtime_manager`` so the post-restart ``lifecycle_state`` is
   correct (A6 boot-safety by design — see
   ``obs-2026-06-01-003-a6-bootstrap-double-init.md`` and A6 §13 in
   ``state.md``).

2. **Lifespan startup** (this coroutine, invoked by uvicorn).
   ``app.state.started_at`` is stamped. If
   ``scheduler_settings.enabled`` is True (B3a; env:
   ``CLAY_SCHEDULER_ENABLED``), a ``ClayScheduler`` is constructed
   from the production module-level service singletons (registry,
   health_monitor, audit_writer, event_bus) and its ``start()`` is
   called. ``start()`` itself transitions the ``session-scheduler``
   service in the registry from ``STOPPED`` (the post-B3a real
   initial state — the pre-B3 fake ``HEALTHY`` stamp was removed) to
   ``HEALTHY`` and writes the ``scheduler.started`` audit event. If
   ``enabled`` is False, the scheduler is **not** constructed; the
   log line is ``info`` (not ``warning``) because this is the
   documented dev-mode path (e.g. ``uvicorn --reload``).

3. **Lifespan shutdown** (this coroutine, on Ctrl-C / SIGTERM). If a
   scheduler was started, ``shutdown(wait=True)`` performs a
   graceful drain (B0 / B3a invariant: no orphan tasks) and walks
   the registry through ``STOPPING`` → ``STOPPED``.

``app.state`` carries references that need to outlive any single
request but are tied to the app lifetime. ``scheduler`` is filled in
by step 2; ``started_at`` is stamped at the same point for
diagnostics.

The decision to keep these references on ``app.state`` (and not, e.g.,
as module-level globals) is so the integration suite in B6 can swap
the production factory with a test factory — A6 lesson: tests and
production must run the **same** wiring path, not a parallel
hand-rolled bundle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import logging

from fastapi import FastAPI

from clay.bootstrap import (
    audit_writer as _audit_writer,
    event_bus as _event_bus,
    health_monitor as _health_monitor,
    ingestion_cycle_service as _ingestion_cycle_service,
    registry as _registry,
    reliability_service as _reliability_service,
    scheduler_settings,
    session_factory as _session_factory,
)
from clay.scheduler.service import ClayScheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup/shutdown hook for non-request work.

    Lifespan runs once per uvicorn process: it yields control to the
    request-handling loop on startup, and reclaims control on
    shutdown. The startup body must remain side-effect-free besides
    the ``app.state`` stamps, the log lines, and the scheduler
    lifecycle call.
    """
    app.state.scheduler = None
    app.state.started_at = None
    logger.info("clay.api.lifespan: startup")
    try:
        app.state.started_at = datetime.now(UTC)
        if scheduler_settings.enabled:
            scheduler = ClayScheduler(
                settings=scheduler_settings,
                registry=_registry,
                health_monitor=_health_monitor,
                audit_writer=_audit_writer,
                event_bus=_event_bus,
                reliability_service=_reliability_service,
                session_factory=_session_factory,
                ingestion_cycle_service=_ingestion_cycle_service,
            )
            scheduler.start()
            app.state.scheduler = scheduler
            logger.info("clay.api.lifespan: scheduler started")
        else:
            app.state.scheduler = None
            logger.info(
                "clay.api.lifespan: scheduler disabled "
                "(CLAY_SCHEDULER_ENABLED=false)"
            )
        yield
    finally:
        if app.state.scheduler is not None:
            app.state.scheduler.shutdown(wait=True)
        logger.info("clay.api.lifespan: shutdown")
        app.state.scheduler = None
        app.state.started_at = None
