from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from clay.bootstrap import (
    control_center_service,
    context_connector_manager,
    event_bus,
    ingestion_cycle_service,
    ingestion_session_factory,
    ingestion_settings,
    market_ingestion_service,
    workspace_service,
)
from clay.control_center.service import ControlCenterService
from clay.events.bus import EventBus
from clay.ingestion.context.manager import ContextConnectorManager
from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import IngestionCycleService
from clay.settings.ingestion import IngestionSettings
from clay.workspace.service import WorkspaceService


def get_ingestion_settings() -> IngestionSettings:
    return ingestion_settings


def get_session_factory() -> sessionmaker:
    return ingestion_session_factory


async def get_db_session() -> Generator[Session, None, None]:
    with ingestion_session_factory() as session:
        yield session


def get_market_ingestion_service() -> MarketIngestionService:
    return market_ingestion_service


def get_context_connector_manager() -> ContextConnectorManager:
    return context_connector_manager


def get_ingestion_cycle_service() -> IngestionCycleService:
    return ingestion_cycle_service


def get_control_center_service() -> ControlCenterService:
    return control_center_service


def get_event_bus() -> EventBus:
    return event_bus


def get_workspace_service() -> WorkspaceService:
    return workspace_service
