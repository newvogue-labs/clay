"""Application bootstrap for the Clay control plane.

`build_services(session_factory)` is the single source of truth for the
Clay service graph: it constructs the registry, runtime manager, and
all 13 services in dependency order, threads the ``session_factory``
through the 5 A3-A5 persisted services, and (when ``session_factory``
is provided) reconciles the ``runtime_manager`` with the restored
``session_state`` row.

The module-level constants at the bottom of the file (the
``alpha_readiness_service`` wiring) expose the production graph to
``api/dependencies.py`` via module-level imports — they call
``build_services(ingestion_session_factory)`` exactly once at import
time. Integration tests call ``build_services`` on a file-based SQLite
in their own helpers (``tests/integration/_helpers.py``) so the
integration suite exercises the **same** wiring as production. This
is what lets the integration suite catch wiring regressions like the
A6-discovered double-init bug (which had silently dropped the
``session_factory`` from the production wiring of
``validation_lab_service`` and ``reliability_service`` while the
A3-A5 unit tests still passed).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import sessionmaker

from clay.ai_control.service import AIControlService
from clay.alpha.service import AlphaReadinessService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.control_center.service import ControlCenterService
from clay.db.session import build_session_factory
from clay.demo_trading.service import DemoTradingService
from clay.events.bus import EventBus
from clay.health.monitor import HealthMonitor
from clay.ingestion.context.connectors.demo_news import DemoNewsConnector
from clay.ingestion.context.connectors.demo_sentiment import DemoSentimentConnector
from clay.ingestion.context.contracts import ContextConnector
from clay.ingestion.context.manager import ContextConnectorManager
from clay.ingestion.market.binance_client import BinanceSpotClient
from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import IngestionCycleService
from clay.knowledge.service import KnowledgeService
from clay.preflight.service import PreflightService
from clay.reliability.service import ReliabilityService
from clay.runtime.manager import RuntimeManager
from clay.session_control.service import SessionControlService
from clay.session_review.service import SessionReviewService
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.services.supervisor import ProcessSupervisor
from clay.signal_engine.service import SignalEngineService
from clay.settings.ingestion import IngestionSettings
from clay.settings.scheduler import SchedulerSettings
from clay.validation_lab.service import ValidationLabService
from clay.workspace.service import WorkspaceService


# B3a: the stale-detection threshold now lives in
# ``SchedulerSettings.health_stale_after_seconds`` (env:
# CLAY_SCHEDULER_HEALTH_STALE_AFTER_SECONDS, default 60) and the
# ``stale_after >= 2 * tick_interval`` invariant is enforced by a
# pydantic ``model_validator`` in ``settings/scheduler.py``. The B2
# hard-coded ``_DEFAULT_HEALTH_STALE_AFTER_SECONDS`` constant has been
# removed.


def _build_default_context_connectors(
    settings: IngestionSettings,
) -> list[ContextConnector]:
    connectors: list[ContextConnector] = []
    if "demo-news" in settings.news_connector_ids:
        connectors.append(DemoNewsConnector())
    if "demo-sentiment" in settings.sentiment_connector_ids:
        connectors.append(DemoSentimentConnector())
    return connectors


def build_services(
    config_loader: ConfigLoader,
    session_factory: sessionmaker | None = None,
    scheduler_settings: SchedulerSettings | None = None,
) -> dict[str, Any]:
    """Build the full Clay service graph.

    ``config_loader`` is **required** (no hidden default) so the
    integration suite can wire an isolated ``ConfigLoader`` rooted at
    a ``tmp_path``-based ``XdgPaths`` without leaking audit/config
    artefacts into the developer's home directory. Production callers
    pass a default ``ConfigLoader()``.

    ``session_factory`` is **optional** (A1-A5 contract): if provided,
    the 5 persisted services (``ai_control``, ``workspace``,
    ``session_control``, ``validation_lab``, ``reliability``) restore
    from the DB on ``__init__``; if ``None``, they fall back to
    in-memory defaults (pre-A3 test pattern).

    ``scheduler_settings`` is **optional** (B3a contract, mirrors
    ``session_factory`` shape): if ``None``, a default
    ``SchedulerSettings()`` is constructed (env-driven via
    ``CLAY_SCHEDULER_*``). The factory uses
    ``scheduler_settings.health_stale_after_seconds`` to wire
    ``HealthMonitor`` — replacing the B2
    ``_DEFAULT_HEALTH_STALE_AFTER_SECONDS`` magic number.

    When ``session_factory is not None``, after all services are
    constructed, ``session_control_service.reconcile_runtime_state()``
    is called to project the restored ``_active_session`` back onto
    ``runtime_manager`` (closes the post-restart
    ``lifecycle_state="review"`` trap from A4 §6 Q2 / A6).

    Order is dependency-driven — services are constructed in
    topological order so that each service's dependencies already
    exist when it is instantiated. The same factory is used by
    production bootstrap and the integration suite.

    Returns a dict of named services keyed by their service-id / role.
    Keys:
        - ``registry``, ``runtime_manager``, ``preflight_service``
        - ``audit_writer``, ``event_bus``,
          ``supervisor``, ``ingestion_settings``, ``session_factory``
        - ``control_center_service``, ``ai_control_service``,
          ``signal_engine_service``, ``workspace_service``,
          ``session_control_service``, ``demo_trading_service``,
          ``session_review_service``, ``knowledge_service``,
          ``validation_lab_service``, ``reliability_service``
        - ``alpha_readiness_service`` (composed at the end from the
          persistent instances of the 6 underlying services).
    """
    config_loader.ensure_default_configs()
    config_loader.load_all()
    audit_writer = AuditWriter(config_loader.paths.state_dir)
    event_bus = EventBus()

    if scheduler_settings is None:
        scheduler_settings = SchedulerSettings()

    registry = ServiceRegistry()
    registry.register(
        service_id="control-api",
        service_type="api",
        criticality=ServiceCriticality.CRITICAL,
        startup_policy="always-on",
    )
    registry.update_status("control-api", ServiceStatus.HEALTHY)
    registry.register(
        service_id="session-scheduler",
        service_type="scheduler",
        criticality=ServiceCriticality.IMPORTANT,
        startup_policy="always-on",
    )
    # B3a: ``session-scheduler`` no longer fakes HEALTHY at import.
    # The status moves through STOPPED → HEALTHY in ``ClayScheduler.start()``
    # (lifespan startup, B3a) and back to STOPPED in
    # ``ClayScheduler.shutdown()``. B3b will add ERROR / STALE on
    # tick exceptions / missed heartbeats.
    registry.register(
        service_id="pair-scanner",
        service_type="worker",
        criticality=ServiceCriticality.OPTIONAL,
        startup_policy="on-demand",
    )

    supervisor = ProcessSupervisor(registry)
    health_monitor = HealthMonitor(
        registry=registry,
        stale_after_seconds=scheduler_settings.health_stale_after_seconds,
    )
    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)

    ingestion_settings = IngestionSettings()
    market_ingestion_service = MarketIngestionService(BinanceSpotClient())

    context_connector_manager = ContextConnectorManager(
        _build_default_context_connectors(ingestion_settings),
    )
    ingestion_cycle_service = IngestionCycleService(
        settings=ingestion_settings,
        market_service=market_ingestion_service,
        context_manager=context_connector_manager,
        audit_writer=audit_writer,
        event_bus=event_bus,
    )

    control_center_service = ControlCenterService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        registry=registry,
        supervisor=supervisor,
        config_loader=config_loader,
        audit_writer=audit_writer,
    )
    ai_control_service = AIControlService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
    )
    signal_engine_service = SignalEngineService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        ai_control_service=ai_control_service,
    )
    workspace_service = WorkspaceService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        registry=registry,
        signal_engine_service=signal_engine_service,
        session_factory=session_factory,
    )
    session_control_service = SessionControlService(
        runtime_manager=runtime_manager,
        signal_engine_service=signal_engine_service,
        ai_control_service=ai_control_service,
        workspace_service=workspace_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
    )
    demo_trading_service = DemoTradingService(
        session_control_service=session_control_service,
        workspace_service=workspace_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
    )
    session_review_service = SessionReviewService(
        audit_writer=audit_writer,
        event_bus=event_bus,
        ai_control_service=ai_control_service,
    )
    knowledge_service = KnowledgeService(
        audit_writer=audit_writer,
        event_bus=event_bus,
    )
    validation_lab_service = ValidationLabService(
        signal_engine_service=signal_engine_service,
        ai_control_service=ai_control_service,
        session_review_service=session_review_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
    )
    reliability_service = ReliabilityService(
        control_center_service=control_center_service,
        ai_control_service=ai_control_service,
        demo_trading_service=demo_trading_service,
        session_review_service=session_review_service,
        validation_lab_service=validation_lab_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
    )

    # A6: when a session_factory is provided, project the restored
    # _active_session back onto runtime_manager so _build_lifecycle
    # returns "active_session" / "paused" (not the false-positive
    # "review" from the BACKGROUND_MONITORING + _active_session
    # fallthrough). No-op when no session was restored. See
    # SessionControlService.reconcile_runtime_state for the rule and
    # the boot-safety contract.
    if session_factory is not None:
        session_control_service.reconcile_runtime_state()

    alpha_readiness_service = AlphaReadinessService(
        workspace_service=workspace_service,
        session_control_service=session_control_service,
        demo_trading_service=demo_trading_service,
        session_review_service=session_review_service,
        validation_lab_service=validation_lab_service,
        reliability_service=reliability_service,
    )

    return {
        "registry": registry,
        "runtime_manager": runtime_manager,
        "preflight_service": preflight_service,
        "scheduler_settings": scheduler_settings,
        "config_loader": config_loader,
        "audit_writer": audit_writer,
        "event_bus": event_bus,
        "supervisor": supervisor,
        "health_monitor": health_monitor,
        "ingestion_settings": ingestion_settings,
        "session_factory": session_factory,
        "market_ingestion_service": market_ingestion_service,
        "context_connector_manager": context_connector_manager,
        "ingestion_cycle_service": ingestion_cycle_service,
        "control_center_service": control_center_service,
        "ai_control_service": ai_control_service,
        "signal_engine_service": signal_engine_service,
        "workspace_service": workspace_service,
        "session_control_service": session_control_service,
        "demo_trading_service": demo_trading_service,
        "session_review_service": session_review_service,
        "knowledge_service": knowledge_service,
        "validation_lab_service": validation_lab_service,
        "reliability_service": reliability_service,
        "alpha_readiness_service": alpha_readiness_service,
    }


# Module-level production wiring — single call to ``build_services`` with
# the production session_factory. ``api/dependencies.py`` imports the
# service instances by name from this module. There is exactly one
# instance of each service in production; alpha_readiness_service is
# built on top of the *persistent* (session_factory-aware) instances
# from the factory — the A6-discovered double-init bug that briefly
# made the second pass of services non-persistent is structurally
# impossible here because there is no second pass.
ingestion_session_factory = build_session_factory(IngestionSettings())
_services = build_services(
    config_loader=ConfigLoader(),
    session_factory=ingestion_session_factory,
)

alpha_readiness_service = _services["alpha_readiness_service"]
ai_control_service = _services["ai_control_service"]
audit_writer = _services["audit_writer"]
config_loader = _services["config_loader"]
context_connector_manager = _services["context_connector_manager"]
control_center_service = _services["control_center_service"]
demo_trading_service = _services["demo_trading_service"]
event_bus = _services["event_bus"]
health_monitor = _services["health_monitor"]
ingestion_cycle_service = _services["ingestion_cycle_service"]
ingestion_settings = _services["ingestion_settings"]
knowledge_service = _services["knowledge_service"]
market_ingestion_service = _services["market_ingestion_service"]
preflight_service = _services["preflight_service"]
registry = _services["registry"]
reliability_service = _services["reliability_service"]
runtime_manager = _services["runtime_manager"]
scheduler_settings = _services["scheduler_settings"]
session_control_service = _services["session_control_service"]
session_factory = _services["session_factory"]
session_review_service = _services["session_review_service"]
signal_engine_service = _services["signal_engine_service"]
supervisor = _services["supervisor"]
validation_lab_service = _services["validation_lab_service"]
workspace_service = _services["workspace_service"]
