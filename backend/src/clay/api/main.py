from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clay.api.lifespan import lifespan
from clay.core.logging import configure_clay_logging
from clay.api.routes.ai_control import router as ai_control_router
from clay.api.routes.ai_control_stream import router as ai_control_stream_router
from clay.api.routes.alpha import router as alpha_router
from clay.api.routes.control_center import router as control_center_router
from clay.api.routes.control_center_stream import router as control_center_stream_router
from clay.api.routes.context_data import router as context_data_router
from clay.api.routes.configs import router as configs_router
from clay.api.routes.demo_trading import router as demo_trading_router
from clay.api.routes.demo_trading_stream import router as demo_trading_stream_router
from clay.api.routes.events import router as events_router
from clay.api.routes.health import router as health_router
from clay.api.routes.ingestion import router as ingestion_router
from clay.api.routes.knowledge import router as knowledge_router
from clay.api.routes.knowledge_stream import router as knowledge_stream_router
from clay.api.routes.market_data import router as market_data_router
from clay.api.routes.preflight import router as preflight_router
from clay.api.routes.reliability import router as reliability_router
from clay.api.routes.reliability_stream import router as reliability_stream_router
from clay.api.routes.runtime import router as runtime_router
from clay.api.routes.session_control import router as session_control_router
from clay.api.routes.session_review import router as session_review_router
from clay.api.routes.session_review_stream import router as session_review_stream_router
from clay.api.routes.session_stream import router as session_stream_router
from clay.api.routes.signals import router as signals_router
from clay.api.routes.shortlist import router as shortlist_router
from clay.api.routes.services import router as services_router
from clay.api.routes.validation_lab import router as validation_lab_router
from clay.api.routes.validation_lab_stream import router as validation_lab_stream_router
from clay.api.routes.workspace import router as workspace_router
from clay.api.routes.workspace_stream import router as workspace_stream_router
from clay.api.routes.override import router as override_router
from clay.api.routes.execution import router as execution_router


def create_app() -> FastAPI:
    """Create and configure the Clay API application.

    Factory function that initialises logging, builds a FastAPI instance
    (title ``"Clay API"``, version ``"0.1.0"``, summary ``"Local control
    plane for Clay"``), configures CORS (dev origins 5173/4173), mounts
    all route routers, and attaches the application lifespan.

    Returns:
        A fully configured FastAPI application ready to serve.
    """
    configure_clay_logging()
    app = FastAPI(
        title="Clay API",
        version="0.1.0",
        summary="Local control plane for Clay",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(ai_control_router)
    app.include_router(ai_control_stream_router)
    app.include_router(alpha_router)
    app.include_router(control_center_router)
    app.include_router(control_center_stream_router)
    app.include_router(configs_router)
    app.include_router(context_data_router)
    app.include_router(demo_trading_router)
    app.include_router(demo_trading_stream_router)
    app.include_router(events_router)
    app.include_router(health_router)
    app.include_router(ingestion_router)
    app.include_router(knowledge_router)
    app.include_router(knowledge_stream_router)
    app.include_router(market_data_router)
    app.include_router(preflight_router)
    app.include_router(reliability_router)
    app.include_router(reliability_stream_router)
    app.include_router(runtime_router)
    app.include_router(session_control_router)
    app.include_router(session_review_router)
    app.include_router(session_review_stream_router)
    app.include_router(session_stream_router)
    app.include_router(signals_router)
    app.include_router(shortlist_router)
    app.include_router(services_router)
    app.include_router(validation_lab_router)
    app.include_router(validation_lab_stream_router)
    app.include_router(workspace_router)
    app.include_router(workspace_stream_router)
    app.include_router(override_router)
    app.include_router(execution_router)
    return app


app = create_app()
