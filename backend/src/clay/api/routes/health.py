import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from clay.bootstrap import ingestion_session_factory
from clay.db.repositories_ops import OpsRepository
from clay.settings.scheduler import SchedulerSettings


router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def get_health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def get_health_ready(request: Request) -> JSONResponse:
    checks: dict[str, str] = {}
    overall_healthy = True

    settings = SchedulerSettings()

    # 1. DB-ping (HARD gate — 503 on failure)
    db_ok = await _check_db()
    checks["database"] = "ok" if db_ok else "down"
    if not db_ok:
        overall_healthy = False

    # 2. Scheduler check (flag-aware)
    scheduler = request.app.state.scheduler
    if not settings.enabled:
        checks["scheduler"] = "disabled"
    elif scheduler is not None and scheduler.is_running:
        checks["scheduler"] = "running"
    else:
        checks["scheduler"] = "stopped"
        overall_healthy = False

    # 3. Ingest freshness (flag-aware + startup-grace)
    if not settings.ingestion_enabled:
        checks["ingest"] = "disabled"
    else:
        checks["ingest"] = await _check_ingest_freshness(
            request.app.state.started_at,
            settings.readiness_stale_threshold_seconds,
        )
        if checks["ingest"] == "stale":
            overall_healthy = False

    status_code = 200 if overall_healthy else 503
    return JSONResponse(
        content={
            "status": "healthy" if overall_healthy else "degraded",
            "checks": checks,
        },
        status_code=status_code,
    )


async def _check_db() -> bool:
    def _ping() -> bool:
        try:
            with ingestion_session_factory() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    return await asyncio.to_thread(_ping)


async def _check_ingest_freshness(
    started_at: datetime | None,
    threshold: int,
) -> str:
    def _query() -> str:
        with ingestion_session_factory() as session:
            repo = OpsRepository(session)
            latest = repo.latest_ingest_run()
        if latest is None:
            return "__null__"
        age = (datetime.now(UTC) - latest.started_at).total_seconds()
        return "stale" if age > threshold else "ok"

    result = await asyncio.to_thread(_query)

    if result == "__null__":
        if (
            started_at is not None
            and (datetime.now(UTC) - started_at).total_seconds() < threshold
        ):
            return "warming_up"
        return "stale"

    return result
