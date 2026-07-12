"""Tests for POST /workspace/trading/execution/testnet-probe (S-TESTNET-1).

Covers:
  - happy-path: testnet mode → 200 + OrderResult fields
  - mode guard: dry_run → 409, live → 409 (place_order NOT called)
  - notional guard: over $50 cap → 422 (create_order NOT called)
  - audit: durable write recorded with correct event_type
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from clay.api.main import create_app
from clay.api.dependencies import get_execution_client, get_execution_config
from clay.execution.config import ExecutionConfig
from clay.execution.exceptions import OrderRejectedError
from clay.execution.models import OrderResult, TradeFill


# ── Helpers ───────────────────────────────────────────────────────


def _make_order_result() -> OrderResult:
    return OrderResult(
        client_order_id="cli_test_001",
        exchange_order_id="exch_test_001",
        symbol="BTCUSDT",
        side="buy",
        quantity=0.001,
        order_type="MARKET",
        status="FILLED",
        transact_time=1700000000000,
        price=50000.0,
        fills=[
            TradeFill(
                trade_id="t1",
                order_id="exch_test_001",
                symbol="BTCUSDT",
                side="buy",
                quantity=0.001,
                price=50000.0,
                commission=0.0000002,
                commission_asset="BTC",
                transact_time=1700000000000,
            )
        ],
    )


def _mock_execution_client(
    *, mode: str = "testnet", result: OrderResult | None = None
) -> tuple[MagicMock, OrderResult]:
    client = MagicMock()
    order_result = result or _make_order_result()
    client.place_order = AsyncMock(return_value=order_result)
    return client, order_result


def _mock_audit_writer() -> MagicMock:
    writer = MagicMock()
    writer.write = MagicMock()
    return writer


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def testnet_config() -> ExecutionConfig:
    return ExecutionConfig(
        mode="testnet",
        api_key="test-key",
        api_secret="test-secret",
        max_order_notional_usdt=50.0,
    )


@pytest.fixture
def dry_run_config() -> ExecutionConfig:
    return ExecutionConfig(mode="dry_run")


@pytest.fixture
def live_config() -> ExecutionConfig:
    return ExecutionConfig(mode="live")


@pytest.fixture
def app():
    application = create_app()
    yield application
    application.dependency_overrides.clear()


# ── Tests ─────────────────────────────────────────────────────────


def test_happy_path_returns_200_with_order_fields(
    app, testnet_config: ExecutionConfig
) -> None:
    mock_client, expected = _mock_execution_client()
    mock_audit = _mock_audit_writer()

    app.dependency_overrides[get_execution_config] = lambda: testnet_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    with patch("clay.api.routes.execution.audit_writer", mock_audit):
        resp = TestClient(app).post(
            "/workspace/trading/execution/testnet-probe",
            json={
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": 0.001,
                "order_type": "MARKET",
                "price": 50000.0,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["client_order_id"] == "cli_test_001"
    assert body["exchange_order_id"] == "exch_test_001"
    assert body["symbol"] == "BTCUSDT"
    assert body["side"] == "buy"
    assert body["quantity"] == 0.001
    assert body["order_type"] == "MARKET"
    assert body["status"] == "FILLED"
    assert body["transact_time"] == 1700000000000
    assert body["price"] == 50000.0
    assert len(body["fills"]) == 1
    assert body["fills"][0]["trade_id"] == "t1"

    mock_client.place_order.assert_awaited_once()


def test_guard_trips_dry_run_returns_409(app, dry_run_config: ExecutionConfig) -> None:
    mock_client, _ = _mock_execution_client()

    app.dependency_overrides[get_execution_config] = lambda: dry_run_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    resp = TestClient(app).post(
        "/workspace/trading/execution/testnet-probe",
        json={
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": 0.001,
            "order_type": "MARKET",
        },
    )

    assert resp.status_code == 409
    assert "testnet" in resp.json()["detail"]
    mock_client.place_order.assert_not_awaited()


def test_guard_trips_live_returns_409(app, live_config: ExecutionConfig) -> None:
    mock_client, _ = _mock_execution_client()

    app.dependency_overrides[get_execution_config] = lambda: live_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    resp = TestClient(app).post(
        "/workspace/trading/execution/testnet-probe",
        json={
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": 0.001,
            "order_type": "MARKET",
        },
    )

    assert resp.status_code == 409
    assert "live" in resp.json()["detail"]
    mock_client.place_order.assert_not_awaited()


def test_notional_over_cap_returns_422(app, testnet_config: ExecutionConfig) -> None:
    mock_client = MagicMock()
    mock_client.place_order = AsyncMock(
        side_effect=OrderRejectedError(
            "order notional 100000.00 USDT exceeds cap 50.00 USDT",
            raw={"notional": 100000.0, "max_notional_usdt": 50.0},
        )
    )

    app.dependency_overrides[get_execution_config] = lambda: testnet_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    resp = TestClient(app).post(
        "/workspace/trading/execution/testnet-probe",
        json={
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": 2.0,
            "order_type": "MARKET",
            "price": 50000.0,
        },
    )

    assert resp.status_code == 422
    assert "exceeds cap" in resp.json()["detail"]
    mock_client.place_order.assert_awaited_once()


def test_audit_recorded_on_success(app, testnet_config: ExecutionConfig) -> None:
    mock_client, expected = _mock_execution_client()
    mock_audit = _mock_audit_writer()

    app.dependency_overrides[get_execution_config] = lambda: testnet_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    with patch("clay.api.routes.execution.audit_writer", mock_audit):
        resp = TestClient(app).post(
            "/workspace/trading/execution/testnet-probe",
            json={
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": 0.001,
                "order_type": "MARKET",
                "price": 50000.0,
            },
        )

    assert resp.status_code == 200

    mock_audit.write.assert_called_once()
    call_args = mock_audit.write.call_args
    assert call_args[0][0] == "execution.testnet_probe"
    payload = call_args[0][1]
    assert payload["actor"] == "operator"
    assert payload["request"]["symbol"] == "BTCUSDT"
    assert payload["result"]["exchange_order_id"] == "exch_test_001"
    assert "fills" in payload["result"]
