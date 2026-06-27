from collections.abc import AsyncGenerator

from sqlalchemy.orm import Session, sessionmaker

from clay.bootstrap import (
    ai_control_service,
    alpha_readiness_service,
    control_center_service,
    context_connector_manager,
    demo_trading_service,
    event_bus,
    execution_client,
    execution_config,
    ingestion_cycle_service,
    ingestion_session_factory,
    ingestion_settings,
    knowledge_service,
    market_ingestion_service,
    override_service,
    reliability_service,
    session_control_service,
    session_review_service,
    signal_engine_service,
    validation_lab_service,
    workspace_service,
)
from clay.ai_control.service import AIControlService
from clay.alpha.service import AlphaReadinessService
from clay.control_center.service import ControlCenterService
from clay.demo_trading.service import DemoTradingService
from clay.events.bus import EventBus
from clay.execution.config import ExecutionConfig
from clay.execution.protocol import ExecutionClient
from clay.execution.service import OverrideService
from clay.ingestion.context.manager import ContextConnectorManager
from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import IngestionCycleService
from clay.knowledge.service import KnowledgeService
from clay.reliability.service import ReliabilityService
from clay.session_control.service import SessionControlService
from clay.session_review.service import SessionReviewService
from clay.signal_engine.service import SignalEngineService
from clay.settings.ingestion import IngestionSettings
from clay.validation_lab.service import ValidationLabService
from clay.workspace.service import WorkspaceService


def get_ingestion_settings() -> IngestionSettings:
    return ingestion_settings


def get_session_factory() -> sessionmaker:
    return ingestion_session_factory


async def get_db_session() -> AsyncGenerator[Session, None]:
    session = ingestion_session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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


def get_ai_control_service() -> AIControlService:
    return ai_control_service


def get_signal_engine_service() -> SignalEngineService:
    return signal_engine_service


def get_session_control_service() -> SessionControlService:
    return session_control_service


def get_demo_trading_service() -> DemoTradingService:
    return demo_trading_service


def get_session_review_service() -> SessionReviewService:
    return session_review_service


def get_knowledge_service() -> KnowledgeService:
    return knowledge_service


def get_validation_lab_service() -> ValidationLabService:
    return validation_lab_service


def get_execution_config() -> ExecutionConfig:
    return execution_config


def get_execution_client() -> ExecutionClient:
    return execution_client


def get_override_service() -> OverrideService:
    return override_service


def get_reliability_service() -> ReliabilityService:
    return reliability_service


def get_alpha_readiness_service() -> AlphaReadinessService:
    return alpha_readiness_service
