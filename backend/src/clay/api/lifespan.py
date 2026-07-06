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
import httpx

from clay.bootstrap import (
    ai_control_service as _ai_control_service,
    audit_writer as _audit_writer,
    event_bus as _event_bus,
    health_monitor as _health_monitor,
    ingestion_cycle_service as _ingestion_cycle_service,
    ingestion_settings as _ingestion_settings,
    knowledge_service as _knowledge_service,
    market_ingestion_service as _market_ingestion_service,
    registry as _registry,
    reliability_service as _reliability_service,
    scheduler_settings,
    session_factory as _session_factory,
)
from clay.ai_control.runner import (
    AgentRunner,
    LiteLLMModelClient,
    OllamaNativeClient,
    RoutingModelClient,
    ServiceModelResolver,
)
from clay.llm import LLMAdapter
from clay.settings.llm import LLMSettings
from clay.scheduler.ai_agent_job import AIAgentCycleJob
from clay.scheduler.provider_pool_reconcile_job import ProviderPoolReconcileJob
from clay.scheduler.service import ClayScheduler
from clay.settings.ollama import OllamaSettings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup/shutdown hook for non-request work.

    Lifespan runs once per uvicorn process: it yields control to the
    request-handling loop on startup, and reclaims control on
    shutdown. The startup body must remain side-effect-free besides
    the ``app.state`` stamps, the log lines, and the scheduler
    lifecycle call.

    C2 (Wave C pre-D hardening): creates a single shared
    ``httpx.AsyncClient`` in startup and injects it into the
    import-time ``MarketIngestionService`` singleton (which
    ``IngestionCycleService``, ``IngestionCycleJob`` and
    ``POST /ingestion/run`` all reach through one DI chain). Closes
    the client in shutdown **after** ``scheduler.shutdown(wait=True)``
    to keep in-flight jobs from racing the close (MED-3). The
    client is bound to the running event loop — never created at
    import time.
    """
    app.state.scheduler = None
    app.state.started_at = None
    http_client: httpx.AsyncClient | None = None
    logger.info("clay.api.lifespan: startup")
    try:
        app.state.started_at = datetime.now(UTC)
        # C2: shared AsyncClient created BEFORE scheduler.start() so jobs
        # see it from their very first tick. Created on the running loop
        # (lifespan runs inside uvicorn's event loop), not at import time.
        http_client = httpx.AsyncClient(
            timeout=_ingestion_settings.market_fetch_timeout,
            limits=httpx.Limits(
                max_connections=_ingestion_settings.market_limits_max_connections,
                max_keepalive_connections=_ingestion_settings.market_limits_max_keepalive,
            ),
        )
        _market_ingestion_service.set_http_client(http_client)
        provider_pool_reconcile_job: ProviderPoolReconcileJob | None = None
        if scheduler_settings.provider_pool_reconcile_enabled:
            provider_pool_reconcile_job = ProviderPoolReconcileJob(
                session_factory=_session_factory,
            )

        ai_agent_cycle_job: AIAgentCycleJob | None = None
        if scheduler_settings.ai_agent_enabled:
            ollama_settings = OllamaSettings()
            ollama_client = OllamaNativeClient.from_settings(ollama_settings)
            llm_settings = LLMSettings()
            llm_client = LiteLLMModelClient(adapter=LLMAdapter(llm_settings))
            router = RoutingModelClient(
                local_client=ollama_client,
                cloud_client=llm_client,
                transport_lookup=_ai_control_service.transport_for,
            )
            resolver = ServiceModelResolver(_ai_control_service)
            runner = AgentRunner(
                model_resolver=resolver,
                model_client=router,
                role_prompts={
                    "market-scanner": (
                        "Ты — market-scanner торговой системы Clay. "
                        "По данным секций market/shortlist выдели: 2–3 наиболее активных символа "
                        "(объём/движение), аномалии свежести данных, кратко riski. "
                        "Формат: маркированный список, ≤150 слов, без советов купить/продать."
                    ),
                    "news-sentiment-agent": (
                        "Ты — news-sentiment-agent системы Clay. "
                        "По секциям news/sentiment: суммируй тональность по символам "
                        "(positive/neutral/negative + одна строка обоснования), "
                        "отметь расхождения news vs sentiment-показателей. ≤150 слов."
                    ),
                },
            )
            ai_agent_cycle_job = AIAgentCycleJob(
                runner=runner,
                session_factory=_session_factory,
                role_ids=scheduler_settings.ai_agent_role_ids,
                ai_control_service=_ai_control_service,
                knowledge_service=_knowledge_service,
                knowledge_mode=scheduler_settings.ai_agent_knowledge_mode,
            )
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
                ai_agent_cycle_job=ai_agent_cycle_job,
                provider_pool_reconcile_job=provider_pool_reconcile_job,
            )
            scheduler.start()
            app.state.scheduler = scheduler
            logger.info("clay.api.lifespan: scheduler started")
        else:
            app.state.scheduler = None
            logger.info(
                "clay.api.lifespan: scheduler disabled (CLAY_SCHEDULER_ENABLED=false)"
            )
        yield
    finally:
        if app.state.scheduler is not None:
            app.state.scheduler.shutdown(wait=True)
        # C2 MED-3: aclose() strictly AFTER scheduler shutdown so in-flight
        # job ticks do not race the close. Guard for the boot-safety case
        # where startup raised before the AsyncClient ctor completed.
        if http_client is not None:
            try:
                await http_client.aclose()
            except Exception:
                logger.exception(
                    "clay.api.lifespan: http_client.aclose failed (known-limit)"
                )
        logger.info("clay.api.lifespan: shutdown")
        app.state.scheduler = None
        app.state.started_at = None
