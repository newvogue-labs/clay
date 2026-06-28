from pathlib import Path

import httpx
import pytest

from clay.api.main import app
from clay.api.routes import configs as configs_route
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths


def build_test_loader(root: Path) -> ConfigLoader:
    paths = XdgPaths(
        config_dir=root / "config",
        data_dir=root / "data",
        state_dir=root / "state",
        cache_dir=root / "cache",
    )
    loader = ConfigLoader(paths=paths)
    loader.write_default_configs()
    loader.load_all()
    return loader


@pytest.mark.anyio
async def test_configs_endpoint_returns_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = build_test_loader(tmp_path)
    monkeypatch.setattr(configs_route, "config_loader", loader)
    monkeypatch.setattr(
        configs_route, "audit_writer", AuditWriter(loader.paths.state_dir)
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/configs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ui_mutable_scopes"] == ["risk", "runtime"]
    assert payload["items"]["runtime"]["default_state"] == "background_monitoring"


@pytest.mark.anyio
async def test_configs_endpoint_applies_valid_runtime_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = build_test_loader(tmp_path)
    monkeypatch.setattr(configs_route, "config_loader", loader)
    monkeypatch.setattr(
        configs_route, "audit_writer", AuditWriter(loader.paths.state_dir)
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/configs/runtime",
            json={
                "config": {
                    "work_window_start": "08:00",
                    "work_window_end": "20:00",
                    "default_state": "background_monitoring",
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["config"]["work_window_start"] == "08:00"
    runtime_config = (loader.paths.config_dir / "runtime.toml").read_text(
        encoding="utf-8"
    )
    assert 'work_window_start = "08:00"' in runtime_config


@pytest.mark.anyio
async def test_configs_endpoint_rejects_invalid_config_and_keeps_last_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = build_test_loader(tmp_path)
    monkeypatch.setattr(configs_route, "config_loader", loader)
    monkeypatch.setattr(
        configs_route, "audit_writer", AuditWriter(loader.paths.state_dir)
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/configs/runtime",
            json={
                "config": {
                    "work_window_start": "08:00",
                    "work_window_end": "20:00",
                    "default_state": "warp_drive",
                },
            },
        )

    assert response.status_code == 400
    runtime_config = (loader.paths.config_dir / "runtime.toml").read_text(
        encoding="utf-8"
    )
    assert 'default_state = "background_monitoring"' in runtime_config
