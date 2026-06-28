"""Tests for ``/health/ready`` (MP2 — readiness probe).

Uses ``create_app()`` directly but patches ``_check_db`` and
``_check_ingest_freshness`` at the module level to avoid real DB.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest

from clay.api.main import create_app
from clay.api.routes import health as health_module
from clay.scheduler.service import ClayScheduler


@pytest.fixture
def app():
    _app = create_app()
    _app.state.scheduler = None
    _app.state.started_at = None
    return _app


@pytest.fixture(autouse=True)
def mock_db_and_ingest():
    """Patch ``_check_db`` and ``_check_ingest_freshness`` to avoid real DB."""

    async def _db_ok() -> bool:
        return True

    async def _ingest_ok(
        started_at: datetime | None,
        threshold: int,
    ) -> str:
        return "ok"

    orig_db = health_module._check_db
    orig_ingest = health_module._check_ingest_freshness
    health_module._check_db = _db_ok  # type: ignore[method-assign]
    health_module._check_ingest_freshness = _ingest_ok  # type: ignore[method-assign]
    yield
    health_module._check_db = orig_db
    health_module._check_ingest_freshness = orig_ingest


@pytest.mark.anyio
async def test_ready_200_when_healthy(app) -> None:
    scheduler = MagicMock(spec=ClayScheduler)
    scheduler.is_running = True
    app.state.scheduler = scheduler
    app.state.started_at = datetime.now(UTC)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["scheduler"] == "running"
    assert data["checks"]["ingest"] == "ok"


@pytest.mark.anyio
async def test_ready_503_when_db_down(app) -> None:
    async def _db_down() -> bool:
        return False

    orig = health_module._check_db
    health_module._check_db = _db_down  # type: ignore[method-assign]
    try:
        scheduler = MagicMock(spec=ClayScheduler)
        scheduler.is_running = True
        app.state.scheduler = scheduler
        app.state.started_at = datetime.now(UTC)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/health/ready")
    finally:
        health_module._check_db = orig

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["database"] == "down"


@pytest.mark.anyio
async def test_ready_503_when_scheduler_stopped(app) -> None:
    app.state.scheduler = None
    app.state.started_at = datetime.now(UTC)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["checks"]["scheduler"] == "stopped"


@pytest.mark.anyio
async def test_ready_scheduler_disabled_not_503(app) -> None:
    import os

    os.environ["CLAY_SCHEDULER_ENABLED"] = "false"
    try:
        app.state.scheduler = None
        app.state.started_at = datetime.now(UTC)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/health/ready")
    finally:
        os.environ.pop("CLAY_SCHEDULER_ENABLED", None)

    assert response.status_code == 200
    data = response.json()
    assert data["checks"]["scheduler"] == "disabled"


@pytest.mark.anyio
async def test_ready_ingest_disabled_not_503(app) -> None:
    import os

    scheduler = MagicMock(spec=ClayScheduler)
    scheduler.is_running = True
    app.state.scheduler = scheduler
    app.state.started_at = datetime.now(UTC)

    os.environ["CLAY_SCHEDULER_INGESTION_ENABLED"] = "false"
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/health/ready")
    finally:
        os.environ.pop("CLAY_SCHEDULER_INGESTION_ENABLED", None)

    assert response.status_code == 200
    data = response.json()
    assert data["checks"]["ingest"] == "disabled"


@pytest.mark.anyio
async def test_ready_warming_up_within_grace(app) -> None:
    async def _warming_up(
        started_at: datetime | None,
        threshold: int,
    ) -> str:
        return "warming_up"

    orig = health_module._check_ingest_freshness
    health_module._check_ingest_freshness = _warming_up  # type: ignore[method-assign]
    try:
        scheduler = MagicMock(spec=ClayScheduler)
        scheduler.is_running = True
        app.state.scheduler = scheduler
        app.state.started_at = datetime.now(UTC)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/health/ready")
    finally:
        health_module._check_ingest_freshness = orig

    assert response.status_code == 200
    data = response.json()
    assert data["checks"]["ingest"] == "warming_up"


@pytest.mark.anyio
async def test_ready_503_when_ingest_stale(app) -> None:
    async def _stale(
        started_at: datetime | None,
        threshold: int,
    ) -> str:
        return "stale"

    orig = health_module._check_ingest_freshness
    health_module._check_ingest_freshness = _stale  # type: ignore[method-assign]
    try:
        scheduler = MagicMock(spec=ClayScheduler)
        scheduler.is_running = True
        app.state.scheduler = scheduler
        app.state.started_at = datetime.now(UTC)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/health/ready")
    finally:
        health_module._check_ingest_freshness = orig

    assert response.status_code == 503
    data = response.json()
    assert data["checks"]["ingest"] == "stale"


@pytest.mark.anyio
async def test_health_liveness_unchanged(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
