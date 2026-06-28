import httpx
import pytest

from clay.api.main import app
from clay.api.routes import services as services_route
from clay.audit.writer import AuditWriter
from clay.config.paths import XdgPaths
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.services.supervisor import ProcessSupervisor


def build_test_registry() -> tuple[ServiceRegistry, ProcessSupervisor]:
    registry = ServiceRegistry()
    registry.register("control-api", "api", ServiceCriticality.CRITICAL, "always-on")
    registry.update_status("control-api", ServiceStatus.HEALTHY)
    registry.register(
        "pair-scanner", "worker", ServiceCriticality.OPTIONAL, "on-demand"
    )
    supervisor = ProcessSupervisor(registry)
    return registry, supervisor


@pytest.mark.anyio
async def test_service_action_endpoint_starts_on_demand_service(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, supervisor = build_test_registry()
    audit_writer = AuditWriter(
        XdgPaths(
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
            state_dir=tmp_path / "state",
            cache_dir=tmp_path / "cache",
        ).state_dir,
    )
    monkeypatch.setattr(services_route, "registry", registry)
    monkeypatch.setattr(services_route, "supervisor", supervisor)
    monkeypatch.setattr(services_route, "audit_writer", audit_writer)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/services/pair-scanner/actions",
            json={"action": "start"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "service_id": "pair-scanner",
        "status": "healthy",
    }


@pytest.mark.anyio
async def test_service_action_endpoint_rejects_control_api_stop(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, supervisor = build_test_registry()
    audit_writer = AuditWriter(
        XdgPaths(
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
            state_dir=tmp_path / "state",
            cache_dir=tmp_path / "cache",
        ).state_dir,
    )
    monkeypatch.setattr(services_route, "registry", registry)
    monkeypatch.setattr(services_route, "supervisor", supervisor)
    monkeypatch.setattr(services_route, "audit_writer", audit_writer)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/services/control-api/actions",
            json={"action": "stop"},
        )

    assert response.status_code == 409
    assert "not allowed" in response.json()["detail"]
