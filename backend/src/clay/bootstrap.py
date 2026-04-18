from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.control_center.service import ControlCenterService
from clay.db.session import build_session_factory
from clay.events.bus import EventBus
from clay.ingestion.context.connectors.demo_news import DemoNewsConnector
from clay.ingestion.context.connectors.demo_sentiment import DemoSentimentConnector
from clay.ingestion.context.contracts import ContextConnector
from clay.ingestion.context.manager import ContextConnectorManager
from clay.ingestion.market.binance_client import BinanceSpotClient
from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import IngestionCycleService
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.services.supervisor import ProcessSupervisor
from clay.settings.ingestion import IngestionSettings
from clay.workspace.service import WorkspaceService


config_loader = ConfigLoader()
config_loader.ensure_default_configs()
config_loader.load_all()
audit_writer = AuditWriter(config_loader.paths.state_dir)
event_bus = EventBus()

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
registry.update_status("session-scheduler", ServiceStatus.HEALTHY)
registry.register(
    service_id="pair-scanner",
    service_type="worker",
    criticality=ServiceCriticality.OPTIONAL,
    startup_policy="on-demand",
)

supervisor = ProcessSupervisor(registry)
runtime_manager = RuntimeManager(registry=registry)
preflight_service = PreflightService(registry)

ingestion_settings = IngestionSettings()
ingestion_session_factory = build_session_factory(ingestion_settings)
market_ingestion_service = MarketIngestionService(BinanceSpotClient())


def build_default_context_connectors(
    settings: IngestionSettings,
) -> list[ContextConnector]:
    connectors: list[ContextConnector] = []
    if "demo-news" in settings.news_connector_ids:
        connectors.append(DemoNewsConnector())
    if "demo-sentiment" in settings.sentiment_connector_ids:
        connectors.append(DemoSentimentConnector())
    return connectors


context_connector_manager = ContextConnectorManager(
    build_default_context_connectors(ingestion_settings),
)
ingestion_cycle_service = IngestionCycleService(
    settings=ingestion_settings,
    market_service=market_ingestion_service,
    context_manager=context_connector_manager,
)
control_center_service = ControlCenterService(
    runtime_manager=runtime_manager,
    preflight_service=preflight_service,
    registry=registry,
    supervisor=supervisor,
    config_loader=config_loader,
    audit_writer=audit_writer,
)
workspace_service = WorkspaceService(
    runtime_manager=runtime_manager,
    preflight_service=preflight_service,
    registry=registry,
)
