"""Tests for POST /workspace/trading/execution/testnet-probe (S-ADAPT-2C, S-ADAPT-3).

Covers:
  - happy-path: testnet mode + FakeBinanceClient → 200 + adapter response fields
  - mode guard: dry_run → 409, live → 409 (place_order NOT called)
  - default-deny: no adapter (None) → 409
  - audit: durable write recorded with correct event_type
  - ambiguous: unresolved AmbiguousExecutionError → 409 + audit (S-ADAPT-3)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from clay.api.dependencies import get_execution_client, get_execution_config
from clay.api.main import create_app
from clay.execution.adapter.binance import BinanceExecutionAdapter
from clay.execution.adapter.enums import (
    Environment,
)
from clay.execution.adapter.errors import AmbiguousExecutionError
from clay.execution.config import ExecutionConfig


# ── FakeBinanceClient (minimal) ───────────────────────────────────


class FakeProbeClient:
    def __init__(self) -> None:
        self._markets: dict[str, Any] = {}
        self._sandbox: bool = False
        self._closed: bool = False

    def set_sandbox_mode(self, enabled: bool) -> None:
        self._sandbox = enabled

    async def load_markets(self) -> dict[str, Any]:
        return self._markets

    async def create_order(
        self,
        *,
        symbol: str,
        type: str,
        side: str,
        amount: str,
        price: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params = params or {}
        return {
            "id": "exch_test_001",
            "clientOrderId": params.get("newClientOrderId", "cli_test_001"),
            "symbol": symbol,
            "side": side,
            "type": type,
            "amount": amount,
            "price": price or "",
            "filled": "0.001",
            "status": "closed",
            "timestamp": 1700000000000,
            "trades": [
                {
                    "id": "t1",
                    "order": "exch_test_001",
                    "symbol": symbol,
                    "side": side,
                    "amount": "0.001",
                    "price": str(price) if price else "0",
                    "commission": "0.0000002",
                    "commissionAsset": "BTC",
                    "timestamp": 1700000000000,
                }
            ],
        }

    async def close(self) -> None:
        self._closed = True

    async def fetch_order(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    async def fetch_open_orders(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return []

    async def fetch_balance(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"total": {}, "free": {}, "used": {}}

    async def cancel_order(self, *args: Any, **kwargs: Any) -> None: ...


# ── Helpers ───────────────────────────────────────────────────────


def _make_client(
    mode: str = "testnet",
    has_creds: bool = True,
) -> BinanceExecutionAdapter | None:
    if mode != "testnet" or not has_creds:
        return None
    client = FakeProbeClient()
    market = {
        "id": "BTCUSDT",
        "symbol": "BTC/USDT",
        "base": "BTC",
        "quote": "USDT",
        "precision": {"amount": "0.001", "price": "0.01"},
        "limits": {
            "amount": {"min": "0.001", "max": "1000"},
            "price": {"min": "0.01", "max": "1000000"},
            "cost": {"min": "10"},
        },
        "info": {
            "filters": [
                {
                    "filterType": "LOT_SIZE",
                    "minQty": "0.001",
                    "maxQty": "1000",
                    "stepSize": "0.001",
                },
                {
                    "filterType": "PRICE_FILTER",
                    "minPrice": "0.01",
                    "maxPrice": "1000000",
                    "tickSize": "0.01",
                },
                {
                    "filterType": "NOTIONAL",
                    "minNotional": "10",
                },
            ]
        },
    }
    client._markets = {"BTCUSDT": market}
    adapter = BinanceExecutionAdapter(Environment.TESTNET, client=client)  # type: ignore[arg-type]
    return adapter


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
        max_order_notional_usdt=Decimal("0"),
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
    mock_client = _make_client(mode="testnet")
    mock_audit = _mock_audit_writer()

    app.dependency_overrides[get_execution_config] = lambda: testnet_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    with patch("clay.api.routes.execution.audit_writer", mock_audit):
        resp = TestClient(app).post(
            "/workspace/trading/execution/testnet-probe",
            json={
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": "0.001",
                "order_type": "market",
            },
        )

    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["client_order_id"] is not None
    assert body["exchange_order_id"] == "exch_test_001"
    assert body["symbol"] == "BTCUSDT"
    assert body["side"] == "buy"
    assert body["quantity"] == "0.001"
    assert body["order_type"] == "market"
    assert body["status"] == "filled"
    assert body["transact_time"] == 1700000000000
    assert len(body["fills"]) == 1
    assert body["fills"][0]["trade_id"] == "t1"


def test_guard_trips_dry_run_returns_409(app, dry_run_config: ExecutionConfig) -> None:
    mock_client = _make_client(mode="dry_run")

    app.dependency_overrides[get_execution_config] = lambda: dry_run_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    resp = TestClient(app).post(
        "/workspace/trading/execution/testnet-probe",
        json={
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.001",
            "order_type": "market",
        },
    )

    assert resp.status_code == 409
    assert "testnet" in resp.json()["detail"]


def test_guard_trips_live_returns_409(app, live_config: ExecutionConfig) -> None:
    mock_client = _make_client(mode="live")

    app.dependency_overrides[get_execution_config] = lambda: live_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    resp = TestClient(app).post(
        "/workspace/trading/execution/testnet-probe",
        json={
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.001",
            "order_type": "market",
        },
    )

    assert resp.status_code == 409
    assert "live" in resp.json()["detail"]


def test_default_deny_no_adapter_returns_409(
    app, testnet_config: ExecutionConfig
) -> None:
    app.dependency_overrides[get_execution_config] = lambda: testnet_config
    app.dependency_overrides[get_execution_client] = lambda: None  # no adapter

    resp = TestClient(app).post(
        "/workspace/trading/execution/testnet-probe",
        json={
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.001",
            "order_type": "market",
        },
    )

    assert resp.status_code == 409
    assert "not armed" in resp.json()["detail"]


def test_audit_recorded_on_success(app, testnet_config: ExecutionConfig) -> None:
    mock_client = _make_client(mode="testnet")
    mock_audit = _mock_audit_writer()

    app.dependency_overrides[get_execution_config] = lambda: testnet_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    with patch("clay.api.routes.execution.audit_writer", mock_audit):
        resp = TestClient(app).post(
            "/workspace/trading/execution/testnet-probe",
            json={
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": "0.001",
                "order_type": "market",
            },
        )

    assert resp.status_code == 200

    mock_audit.write.assert_called_once()
    call_args = mock_audit.write.call_args
    assert call_args[0][0] == "execution.testnet_probe"
    payload = call_args[0][1]
    assert payload["actor"] == "operator"
    assert payload["request"]["symbol"] == "BTCUSDT"
    assert payload["result"]["venue_order_id"] == "exch_test_001"
    assert "fills_count" in payload["result"]


def test_response_fields_are_strings_not_floats(
    app, testnet_config: ExecutionConfig
) -> None:
    mock_client = _make_client(mode="testnet")
    mock_audit = _mock_audit_writer()

    app.dependency_overrides[get_execution_config] = lambda: testnet_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    with patch("clay.api.routes.execution.audit_writer", mock_audit):
        resp = TestClient(app).post(
            "/workspace/trading/execution/testnet-probe",
            json={
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": "0.001",
                "order_type": "market",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["quantity"], str)
    assert isinstance(body["fills"][0]["quantity"], str)
    assert isinstance(body["fills"][0]["price"], str)
    assert isinstance(body["fills"][0]["commission"], str)


def test_notional_cap_over_returns_422(app, testnet_config: ExecutionConfig) -> None:
    cap_config = ExecutionConfig(
        mode="testnet",
        api_key="test-key",
        api_secret="test-secret",
        max_order_notional_usdt=Decimal("0.01"),
    )
    mock_client = _make_client(mode="testnet")
    from clay.execution.proof.gate import ExecutionProofGate
    from clay.execution.proof.snapshot import FreshnessPolicy

    gated_client = ExecutionProofGate(
        mock_client,
        session_factory=None,
        freshness_policy=FreshnessPolicy(max_age_seconds=300),
        max_order_notional=cap_config.max_order_notional_usdt,
    )

    app.dependency_overrides[get_execution_config] = lambda: cap_config
    app.dependency_overrides[get_execution_client] = lambda: gated_client

    resp = TestClient(app).post(
        "/workspace/trading/execution/testnet-probe",
        json={
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "100",
            "order_type": "market",
            "price": "1.00",
        },
    )

    assert resp.status_code == 422


def test_notional_cap_off_by_default_returns_200(
    app, testnet_config: ExecutionConfig
) -> None:
    zero_cap_config = ExecutionConfig(
        mode="testnet",
        api_key="test-key",
        api_secret="test-secret",
        max_order_notional_usdt=Decimal("0"),
    )
    mock_client = _make_client(mode="testnet")

    app.dependency_overrides[get_execution_config] = lambda: zero_cap_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    resp = TestClient(app).post(
        "/workspace/trading/execution/testnet-probe",
        json={
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "100",
            "order_type": "market",
            "price": "1.00",
        },
    )

    assert resp.status_code == 200


def test_notional_cap_fail_closed_market_no_price(
    app, testnet_config: ExecutionConfig
) -> None:
    """Cap active + market order without price → fail-closed 422."""
    cap_config = ExecutionConfig(
        mode="testnet",
        api_key="test-key",
        api_secret="test-secret",
        max_order_notional_usdt=Decimal("50"),
    )
    mock_client = _make_client(mode="testnet")
    from clay.execution.proof.gate import ExecutionProofGate
    from clay.execution.proof.snapshot import FreshnessPolicy

    gated_client = ExecutionProofGate(
        mock_client,
        session_factory=None,
        freshness_policy=FreshnessPolicy(max_age_seconds=300),
        max_order_notional=cap_config.max_order_notional_usdt,
    )

    app.dependency_overrides[get_execution_config] = lambda: cap_config
    app.dependency_overrides[get_execution_client] = lambda: gated_client

    resp = TestClient(app).post(
        "/workspace/trading/execution/testnet-probe",
        json={
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.001",
            "order_type": "market",
        },
    )

    assert resp.status_code == 422


def test_ambiguous_execution_returns_409_with_audit(
    app, testnet_config: ExecutionConfig
) -> None:
    """Unresolved AmbiguousExecutionError → HTTP 409 + audit write."""
    mock_audit = _mock_audit_writer()

    # Use real adapter (handles get_market_rules), patch place_order to raise
    mock_client = _make_client(mode="testnet")
    assert mock_client is not None

    async def _raise_ambiguous(req: Any) -> Any:
        raise AmbiguousExecutionError("connection timeout")

    mock_client.place_order = _raise_ambiguous  # type: ignore[assignment]

    app.dependency_overrides[get_execution_config] = lambda: testnet_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    with patch("clay.api.routes.execution.audit_writer", mock_audit):
        resp = TestClient(app).post(
            "/workspace/trading/execution/testnet-probe",
            json={
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": "0.001",
                "order_type": "market",
            },
        )

    assert resp.status_code == 409
    assert "reconcile pending" in resp.json()["detail"]

    # Audit should have been written with ambiguous event type
    mock_audit.write.assert_called_once()
    call_args = mock_audit.write.call_args
    assert call_args[0][0] == "execution.testnet_probe_ambiguous"
    payload = call_args[0][1]
    assert payload["actor"] == "operator"
    assert payload["cid"] is not None
    assert payload["symbol"] == "BTCUSDT"


def test_circuit_open_returns_503_with_audit(
    app, testnet_config: ExecutionConfig
) -> None:
    """CircuitOpenError → HTTP 503 + audit write."""
    from clay.execution.adapter.errors import CircuitOpenError

    mock_audit = _mock_audit_writer()

    mock_client = _make_client(mode="testnet")
    assert mock_client is not None

    async def _raise_circuit_open(req: Any) -> Any:
        raise CircuitOpenError("circuit open, retry after 28.5s")

    mock_client.place_order = _raise_circuit_open  # type: ignore[assignment]

    app.dependency_overrides[get_execution_config] = lambda: testnet_config
    app.dependency_overrides[get_execution_client] = lambda: mock_client

    with patch("clay.api.routes.execution.audit_writer", mock_audit):
        resp = TestClient(app).post(
            "/workspace/trading/execution/testnet-probe",
            json={
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": "0.001",
                "order_type": "market",
            },
        )

    assert resp.status_code == 503
    assert "venue degraded" in resp.json()["detail"]

    mock_audit.write.assert_called_once()
    call_args = mock_audit.write.call_args
    assert call_args[0][0] == "execution.testnet_probe_circuit_open"
    payload = call_args[0][1]
    assert payload["actor"] == "operator"
    assert payload["symbol"] == "BTCUSDT"


def _make_rules_from_client() -> Any:
    """Build a MarketRules-compatible object from FakeProbeClient data."""
    from clay.execution.adapter.rules import MarketRules as RealRules
    from clay.execution.adapter.enums import PrecisionMode, OrderType, TimeInForce

    return RealRules(
        min_amount=Decimal("0.001"),
        max_amount=Decimal("1000"),
        min_price=Decimal("0.01"),
        max_price=Decimal("1000000"),
        min_notional=Decimal("10"),
        amount_step=Decimal("0.001"),
        price_tick=Decimal("0.01"),
        precision_mode=PrecisionMode.TICK_SIZE,
        supported_order_types=frozenset(
            {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT}
        ),
        supported_tif=frozenset({TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK}),
    )
