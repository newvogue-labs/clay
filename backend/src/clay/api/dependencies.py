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
    """Return the ingestion settings singleton."""
    return ingestion_settings


def get_session_factory() -> sessionmaker:
    """Return the SQLAlchemy session factory for ingestion."""
    return ingestion_session_factory


async def get_db_session() -> AsyncGenerator[Session, None]:
    """FastAPI dependency that yields a database session.

    Yields an SQLAlchemy Session from the ingestion session factory.
    Commits on success, rolls back on exception, and always closes
    the session in the ``finally`` block.

    Yields:
        An open SQLAlchemy Session bound to the ingestion database.

    Raises:
        RuntimeError: If the session factory fails to produce a session.
    """
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
    """Return the market data ingestion service."""
    return market_ingestion_service


def get_context_connector_manager() -> ContextConnectorManager:
    """Return the context connector manager for external data feeds."""
    return context_connector_manager


def get_ingestion_cycle_service() -> IngestionCycleService:
    """Return the ingestion cycle orchestrator."""
    return ingestion_cycle_service


def get_control_center_service() -> ControlCenterService:
    """Return the control center service for dashboard aggregation."""
    return control_center_service


def get_event_bus() -> EventBus:
    """Return the in-process event bus."""
    return event_bus


def get_workspace_service() -> WorkspaceService:
    """Return the workspace state service."""
    return workspace_service


def get_ai_control_service() -> AIControlService:
    """Return the AI-control orchestration service."""
    return ai_control_service


def get_signal_engine_service() -> SignalEngineService:
    """Return the signal engine service for scoring and ranking."""
    return signal_engine_service


def get_session_control_service() -> SessionControlService:
    """Return the session control service for lifecycle management."""
    return session_control_service


def get_demo_trading_service() -> DemoTradingService:
    """Return the demo trading service for paper-trading simulation."""
    return demo_trading_service


def get_session_review_service() -> SessionReviewService:
    """Return the session review service for post-session analysis."""
    return session_review_service


def get_knowledge_service() -> KnowledgeService:
    """Return the knowledge retrieval service (advisory, off hot-path)."""
    return knowledge_service


def get_validation_lab_service() -> ValidationLabService:
    """Return the validation lab service for model activation promotion."""
    return validation_lab_service


def get_execution_config() -> ExecutionConfig:
    """Return the execution configuration (testnet parameters)."""
    return execution_config


def get_execution_client() -> ExecutionClient:
    """Return the execution client for order placement."""
    return execution_client


def get_override_service() -> OverrideService:
    """Return the execution override service for manual trade control."""
    return override_service


def get_reliability_service() -> ReliabilityService:
    """Return the reliability monitoring service."""
    return reliability_service


def get_alpha_readiness_service() -> AlphaReadinessService:
    """Return the alpha readiness assessment service."""
    return alpha_readiness_service
