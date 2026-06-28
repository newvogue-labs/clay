"""Tests for execution-aware workspace state."""

from unittest.mock import MagicMock, patch

import pytest

from clay.execution.config import ExecutionConfig
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.registry import ServiceRegistry
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService
from clay.workspace.models import WorkspaceStateSnapshot


@pytest.fixture
def mock_repositories():
    with (
        patch("clay.workspace.service.MarketRepository") as market_cls,
        patch("clay.workspace.service.ContextRepository") as ctx_cls,
        patch("clay.workspace.service.OpsRepository") as ops_cls,
        patch("clay.workspace.service.resolve_market_freshness_status") as resolve_mock,
        patch("clay.workspace.service.collapse_market_statuses", return_value="fresh"),
    ):
        market_cls.return_value.list_freshness_statuses.return_value = []
        market_cls.return_value.list_latest_bars.return_value = []
        ctx_cls.return_value.latest_news.return_value = []
        ctx_cls.return_value.latest_sentiment.return_value = []
        ops_cls.return_value.latest_connector_statuses.return_value = []
        resolve_mock.return_value.status = "fresh"
        yield


def _build_service(execution_config: ExecutionConfig | None = None):
    runtime_manager = MagicMock(spec=RuntimeManager)
    runtime_manager.snapshot.return_value.state.value = "background_monitoring"
    preflight = MagicMock(spec=PreflightService)
    preflight.run.return_value.status = "pass"
    registry = MagicMock(spec=ServiceRegistry)
    signal_engine = MagicMock(spec=SignalEngineService)
    signal_engine.build_snapshot.return_value.signals = []
    return WorkspaceService(
        runtime_manager=runtime_manager,
        preflight_service=preflight,
        registry=registry,
        signal_engine_service=signal_engine,
        session_factory=None,
        execution_config=execution_config,
    )


def _snapshot(service: WorkspaceService, session) -> WorkspaceStateSnapshot:
    state, *_ = service._build_workspace_state(session)
    return state


def test_dry_run_allows_open(mock_repositories) -> None:
    service = _build_service(ExecutionConfig(mode="dry_run"))
    session = MagicMock()
    state = _snapshot(service, session)
    assert state.can_open_binance is True
    assert state.execution_mode == "dry_run"
    assert state.blocking_reason is None


def test_testnet_allows_open(mock_repositories) -> None:
    service = _build_service(ExecutionConfig(mode="testnet"))
    session = MagicMock()
    state = _snapshot(service, session)
    assert state.can_open_binance is True
    assert state.execution_mode == "testnet"
    assert state.blocking_reason is None


def test_live_without_override_blocks(mock_repositories) -> None:
    service = _build_service(ExecutionConfig(mode="live"))
    session = MagicMock()
    state = _snapshot(service, session)
    assert state.can_open_binance is False
    assert state.execution_mode == "live"
    assert (
        state.blocking_reason == "Live execution requires Q5 override (not confirmed)"
    )
