"""Integration tests for override API endpoints (S-EXEC-3b-3).

Scope:
- Direct handler unit tests (route handlers + OverrideService state machine)
- App-level integration tests through FastAPI with app_with_sqlite (B1)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from clay.api.main import create_app
from fastapi import HTTPException

from clay.api.routes.override import (
    OverrideConfirmPayload,
    OverrideRequestPayload,
    OverrideRevokePayload,
    confirm_override,
    request_override,
    revoke_override,
)
from clay.execution.config import ExecutionConfig
from clay.execution.service import OverrideService


@pytest.fixture
def app():
    application = create_app()
    test_service = OverrideService(
        session_factory=None,
        audit_writer=None,
        execution_config=ExecutionConfig(mode="live", allow_live_override=True),
    )
    from clay.api.dependencies import get_override_service

    application.dependency_overrides[get_override_service] = lambda: test_service
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app)


def build_override_service() -> OverrideService:
    return OverrideService(
        session_factory=None,
        audit_writer=None,
        execution_config=ExecutionConfig(mode="live", allow_live_override=True),
    )


# ── direct handler unit tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_override_request_returns_pending_state(db_session: Session) -> None:
    svc = build_override_service()
    response = await request_override(
        OverrideRequestPayload(actor="op-1", reason="fire drill"),
        svc,
    )
    assert response.status == "pending"
    assert response.override_id is not None
    assert response.override_id.startswith("ovr_")


@pytest.mark.asyncio
async def test_override_confirm_sets_confirmed(db_session: Session) -> None:
    svc = build_override_service()
    req = await request_override(
        OverrideRequestPayload(actor="op-1", reason="r1"),
        svc,
    )
    oid = req.override_id

    conf = await confirm_override(
        OverrideConfirmPayload(actor="op-2", reason="go"),
        svc,
    )
    assert conf.status == "confirmed"
    assert conf.override_id == oid
    assert conf.expires_at is not None
    assert svc.armed_override_id == oid


@pytest.mark.asyncio
async def test_override_revoke_clears_state(db_session: Session) -> None:
    svc = build_override_service()
    await request_override(
        OverrideRequestPayload(actor="op-1", reason="r1"),
        svc,
    )
    await confirm_override(
        OverrideConfirmPayload(actor="op-2", reason="go"),
        svc,
    )
    assert svc.armed_override_id is not None

    res = await revoke_override(
        OverrideRevokePayload(actor="op-1", reason="abort"),
        svc,
    )
    assert res.status is None
    assert svc.armed_override_id is None


@pytest.mark.asyncio
async def test_full_lifecycle_request_confirm_revoke(db_session: Session) -> None:
    svc = build_override_service()

    req = await request_override(
        OverrideRequestPayload(actor="op-1", reason="fire drill"),
        svc,
    )
    assert req.status == "pending"
    oid = req.override_id

    conf = await confirm_override(
        OverrideConfirmPayload(actor="op-2", reason="go"),
        svc,
    )
    assert conf.status == "confirmed"
    assert svc.armed_override_id == oid

    rev = await revoke_override(
        OverrideRevokePayload(actor="op-1", reason="all clear"),
        svc,
    )
    assert rev.status is None
    assert svc.armed_override_id is None


@pytest.mark.asyncio
async def test_confirm_rejects_when_not_pending(db_session: Session) -> None:
    svc = build_override_service()
    with pytest.raises(HTTPException) as exc_info:
        await confirm_override(
            OverrideConfirmPayload(actor="op-2"),
            svc,
        )
    assert exc_info.value.status_code == 422
    assert "not pending" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_revoke_rejects_when_no_active_override(db_session: Session) -> None:
    svc = build_override_service()
    with pytest.raises(HTTPException) as exc_info:
        await revoke_override(
            OverrideRevokePayload(actor="op-1", reason="x"),
            svc,
        )
    assert exc_info.value.status_code == 422
    assert "no active override" in str(exc_info.value.detail)


# ── FastAPI integration tests (B1: wiring coverage) ─────────────────────────


def test_override_request_endpoint_roundtrip(client: TestClient) -> None:
    payload = {"actor": "operator-1", "reason": "maintenance window"}
    response = client.post("/workspace/trading/override/request", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["override_id"].startswith("ovr_")


def test_override_confirm_endpoint_roundtrip(client: TestClient) -> None:
    req_resp = client.post(
        "/workspace/trading/override/request",
        json={"actor": "op-1", "reason": "r1"},
    )
    assert req_resp.status_code == 200
    oid = req_resp.json()["override_id"]

    conf_resp = client.post(
        "/workspace/trading/override/confirm",
        json={"actor": "op-2", "reason": "approved"},
    )
    assert conf_resp.status_code == 200
    conf_body = conf_resp.json()
    assert conf_body["override_id"] == oid
    assert conf_body["status"] == "confirmed"
    assert conf_body["expires_at"] is not None


def test_override_revoke_endpoint_roundtrip(client: TestClient) -> None:
    client.post(
        "/workspace/trading/override/request",
        json={"actor": "op-1", "reason": "r1"},
    )
    client.post(
        "/workspace/trading/override/confirm",
        json={"actor": "op-2", "reason": "approved"},
    )

    rev_resp = client.post(
        "/workspace/trading/override/revoke",
        json={"actor": "op-1", "reason": "abort"},
    )
    assert rev_resp.status_code == 200
    assert rev_resp.json()["status"] is None


def test_override_lifecycle_full_http(client: TestClient) -> None:
    req = client.post(
        "/workspace/trading/override/request",
        json={"actor": "op-1", "reason": "fire drill"},
    )
    assert req.status_code == 200

    conf = client.post(
        "/workspace/trading/override/confirm",
        json={"actor": "op-2", "reason": "go"},
    )
    assert conf.status_code == 200
    assert conf.json()["status"] == "confirmed"

    rev = client.post(
        "/workspace/trading/override/revoke",
        json={"actor": "op-1", "reason": "done"},
    )
    assert rev.status_code == 200
    assert rev.json()["status"] is None


def test_override_confirm_422_when_not_pending(client: TestClient) -> None:
    response = client.post(
        "/workspace/trading/override/confirm",
        json={"actor": "op-2"},
    )
    assert response.status_code == 422


def test_override_revoke_422_when_no_active(client: TestClient) -> None:
    response = client.post(
        "/workspace/trading/override/revoke",
        json={"actor": "op-1", "reason": "x"},
    )
    assert response.status_code == 422


def test_b1_residual_confirm_sets_workspace_gate(app_with_sqlite) -> None:
    """Confirm override → workspace.execution_override_state=confirmed (real wiring).

    Uses module-level ``override_service`` / ``workspace_service`` (no dependency_overrides).
    Patches execution_config in-place so ``_is_live_config()`` returns True;
    restores original config via try/finally to avoid state leak.
    """
    import clay.bootstrap as _bs
    from clay.execution.config import ExecutionConfig

    original_cfg = _bs.override_service._execution_config
    live_cfg = ExecutionConfig(mode="live", allow_live_override=True)
    object.__setattr__(_bs.override_service, "_execution_config", live_cfg)
    _bs.override_service.rehydrate()

    try:
        # Без dependency_overrides: зависимости FastAPI берут module-level singleton
        # (app_with_sqlite оставляет только get_db_session override)
        client = TestClient(app_with_sqlite)

        # 1) request
        r = client.post(
            "/workspace/trading/override/request",
            json={"actor": "op-1", "reason": "t"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

        # 2) confirm → проверяем JSON AND workspace snapshot (D4 manual-only через HTTP)
        c = client.post(
            "/workspace/trading/override/confirm",
            json={"actor": "op-2", "reason": "go"},
        )
        assert c.status_code == 200
        assert c.json()["status"] == "confirmed"
        assert c.json()["override_id"] is not None

        snap = client.get("/workspace/trading").json()
        assert snap["workspace_state"]["execution_override_state"] == "confirmed"

        # 3) revoke очищает и override, и workspace gate
        rv = client.post(
            "/workspace/trading/override/revoke",
            json={"actor": "op-1", "reason": "done"},
        )
        assert rv.status_code == 200
        assert rv.json()["status"] is None

        snap = client.get("/workspace/trading").json()
        assert snap["workspace_state"]["execution_override_state"] is None
    finally:
        object.__setattr__(_bs.override_service, "_execution_config", original_cfg)
        _bs.override_service.rehydrate()
