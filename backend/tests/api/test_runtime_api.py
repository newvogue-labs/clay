import httpx
import pytest

from clay.api.main import app
from clay.api.routes import runtime as runtime_route
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry


@pytest.mark.anyio
async def test_runtime_state_endpoint_returns_bootstrap_state() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/runtime/state")

        assert response.status_code == 200
        assert response.json()["state"] == "background_monitoring"
        assert response.json()["allowed_transitions"] == [
            "pre_session",
            "degraded",
        ]


@pytest.mark.anyio
async def test_runtime_transition_endpoint_updates_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ServiceRegistry()
    registry.register("control-api", "api", ServiceCriticality.CRITICAL, "always-on")
    registry.update_status("control-api", ServiceStatus.HEALTHY)
    manager = RuntimeManager(registry=registry)
    monkeypatch.setattr(runtime_route, "runtime_manager", manager)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/runtime/transition", json={"target": "pre_session"}
        )

    assert response.status_code == 200
    assert response.json()["state"] == "pre_session"
