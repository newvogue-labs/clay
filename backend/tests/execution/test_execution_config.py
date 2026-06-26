"""Tests for execution config and factory."""

import os

import pytest

from clay.execution.config import ExecutionConfig
from clay.execution.exceptions import ExecutionConfigError
from clay.execution.factory import build_execution_client


def test_default_execution_config_is_dry_run() -> None:
    config = ExecutionConfig()
    assert config.mode == "dry_run"
    assert config.allow_live_override is False


def test_execution_config_from_env_defaults_to_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAY_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("CLAY_BINANCE_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("CLAY_BINANCE_TESTNET_API_SECRET", raising=False)
    config = ExecutionConfig.from_env()
    assert config.mode == "dry_run"


def test_execution_config_from_env_respects_testnet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAY_EXECUTION_MODE", "testnet")
    monkeypatch.setenv("CLAY_BINANCE_TESTNET_API_KEY", "k")
    monkeypatch.setenv("CLAY_BINANCE_TESTNET_API_SECRET", "s")
    config = ExecutionConfig.from_env()
    assert config.mode == "testnet"
    assert config.api_key == "k"
    assert config.api_secret == "s"


def test_execution_config_invalid_mode_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAY_EXECUTION_MODE", "live")
    config = ExecutionConfig.from_env()
    assert config.mode == "dry_run"


def test_build_execution_client_dry_run() -> None:
    client = build_execution_client(mode="dry_run")
    assert client.SOURCE == "dry_run"


def test_build_execution_client_testnet_missing_keys_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAY_BINANCE_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("CLAY_BINANCE_TESTNET_API_SECRET", raising=False)
    with pytest.raises(ExecutionConfigError, match="required"):
        build_execution_client(mode="testnet")


def test_build_execution_client_live_raises() -> None:
    with pytest.raises(ExecutionConfigError, match="not implemented"):
        build_execution_client(mode="live")
