"""Tests for execution-aware workspace state."""

from unittest.mock import MagicMock

import pytest

from clay.execution.config import ExecutionConfig
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.registry import ServiceRegistry
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService
from clay.workspace.models import WorkspaceStateSnapshot


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


def test_dry_run_allows_open(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(ExecutionConfig(mode="dry_run"))
    session = MagicMock()
    state = _snapshot(service, session)
    assert state.can_open_binance is True
    assert state.execution_mode == "dry_run"
    assert state.blocking_reason is None


def test_testnet_allows_open(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(ExecutionConfig(mode="testnet"))
    session = MagicMock()
    state = _snapshot(service, session)
    assert state.can_open_binance is True
    assert state.execution_mode == "testnet"
    assert state.blocking_reason is None


def test_live_without_override_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(ExecutionConfig(mode="live", override_state=None))
    session = MagicMock()
    state = _snapshot(service, session)
    assert state.can_open_binance is False
    assert state.execution_mode == "live"
    assert state.blocking_reason == "Live execution requires Q5 override (not confirmed)"
