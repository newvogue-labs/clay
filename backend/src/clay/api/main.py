from fastapi import FastAPI

from clay.api.routes.ai_control import router as ai_control_router
from clay.api.routes.ai_control_stream import router as ai_control_stream_router
from clay.api.routes.control_center import router as control_center_router
from clay.api.routes.control_center_stream import router as control_center_stream_router
from clay.api.routes.context_data import router as context_data_router
from clay.api.routes.configs import router as configs_router
from clay.api.routes.events import router as events_router
from clay.api.routes.health import router as health_router
from clay.api.routes.ingestion import router as ingestion_router
from clay.api.routes.market_data import router as market_data_router
from clay.api.routes.preflight import router as preflight_router
from clay.api.routes.runtime import router as runtime_router
from clay.api.routes.signals import router as signals_router
from clay.api.routes.shortlist import router as shortlist_router
from clay.api.routes.services import router as services_router
from clay.api.routes.workspace import router as workspace_router
from clay.api.routes.workspace_stream import router as workspace_stream_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clay API",
        version="0.1.0",
        summary="Local control plane for Clay",
    )
    app.include_router(ai_control_router)
    app.include_router(ai_control_stream_router)
    app.include_router(control_center_router)
    app.include_router(control_center_stream_router)
    app.include_router(configs_router)
    app.include_router(context_data_router)
    app.include_router(events_router)
    app.include_router(health_router)
    app.include_router(ingestion_router)
    app.include_router(market_data_router)
    app.include_router(preflight_router)
    app.include_router(runtime_router)
    app.include_router(signals_router)
    app.include_router(shortlist_router)
    app.include_router(services_router)
    app.include_router(workspace_router)
    app.include_router(workspace_stream_router)
    return app


app = create_app()
