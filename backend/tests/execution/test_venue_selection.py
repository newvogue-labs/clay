"""Tests for venue selection (D5) — bybit|binance in bootstrap, demo mode.

All tests are hermetic: monkeypatch on env, no real keys, no network.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from clay.execution.adapter.binance import BinanceExecutionAdapter
from clay.execution.adapter.bybit import BybitExecutionAdapter
from clay.execution.adapter.enums import Environment
from clay.execution.config import (
    ExecutionConfig,
    _resolve_credentials,
    environment_from_mode,
)


# ---------------------------------------------------------------------------
# environment_from_mode (D2)
# ---------------------------------------------------------------------------


class TestEnvironmentFromMode:
    def test_testnet(self) -> None:
        assert environment_from_mode("testnet") == Environment.TESTNET

    def test_demo(self) -> None:
        assert environment_from_mode("demo") == Environment.DEMO

    def test_dry_run_returns_none(self) -> None:
        assert environment_from_mode("dry_run") is None

    def test_live_returns_none(self) -> None:
        assert environment_from_mode("live") is None

    def test_unknown_returns_none(self) -> None:
        assert environment_from_mode("bogus") is None


# ---------------------------------------------------------------------------
# from_env: venue (D1)
# ---------------------------------------------------------------------------


class TestFromEnvVenue:
    def test_default_venue(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAY_EXECUTION_VENUE", None)
            cfg = ExecutionConfig.from_env()
            assert cfg.venue == "binance"

    def test_venue_bybit(self) -> None:
        with patch.dict(os.environ, {"CLAY_EXECUTION_VENUE": "bybit"}):
            cfg = ExecutionConfig.from_env()
            assert cfg.venue == "bybit"

    def test_unknown_venue_reverts_to_binance(self) -> None:
        with patch.dict(os.environ, {"CLAY_EXECUTION_VENUE": "kraken"}):
            cfg = ExecutionConfig.from_env()
            assert cfg.venue == "binance"

    def test_unknown_venue_warns(self) -> None:
        with patch.dict(os.environ, {"CLAY_EXECUTION_VENUE": "kraken"}):
            with patch("clay.execution.config.logger") as mock_log:
                ExecutionConfig.from_env()
                mock_log.warning.assert_called()
                call_str = str(mock_log.warning.call_args)
                assert "kraken" in call_str


# ---------------------------------------------------------------------------
# from_env: mode (D1)
# ---------------------------------------------------------------------------


class TestFromEnvMode:
    def test_default_mode(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAY_EXECUTION_MODE", None)
            cfg = ExecutionConfig.from_env()
            assert cfg.mode == "dry_run"

    def test_mode_demo_accepted(self) -> None:
        with patch.dict(os.environ, {"CLAY_EXECUTION_MODE": "demo"}):
            cfg = ExecutionConfig.from_env()
            assert cfg.mode == "demo"

    def test_mode_live_reverts_to_dry_run(self) -> None:
        with patch.dict(os.environ, {"CLAY_EXECUTION_MODE": "live"}):
            cfg = ExecutionConfig.from_env()
            assert cfg.mode == "dry_run"

    def test_mode_live_warns(self) -> None:
        with patch.dict(os.environ, {"CLAY_EXECUTION_MODE": "live"}):
            with patch("clay.execution.config.logger") as mock_log:
                ExecutionConfig.from_env()
                mock_log.warning.assert_called()
                call_str = str(mock_log.warning.call_args)
                assert "live" in call_str


# ---------------------------------------------------------------------------
# _resolve_credentials (D1)
# ---------------------------------------------------------------------------


class TestResolveCredentials:
    def test_binance_testnet(self) -> None:
        env = {
            "CLAY_BINANCE_TESTNET_API_KEY": "bk",
            "CLAY_BINANCE_TESTNET_API_SECRET": "bs",
        }
        with patch.dict(os.environ, env, clear=False):
            k, s = _resolve_credentials("binance", "testnet")
            assert k == "bk"
            assert s == "bs"

    def test_bybit_testnet(self) -> None:
        env = {
            "CLAY_BYBIT_TESTNET_API_KEY": "tk",
            "CLAY_BYBIT_TESTNET_API_SECRET": "ts",
        }
        with patch.dict(os.environ, env, clear=False):
            k, s = _resolve_credentials("bybit", "testnet")
            assert k == "tk"
            assert s == "ts"

    def test_bybit_demo(self) -> None:
        env = {
            "CLAY_BYBIT_DEMO_API_KEY": "dk",
            "CLAY_BYBIT_DEMO_API_SECRET": "ds",
        }
        with patch.dict(os.environ, env, clear=False):
            k, s = _resolve_credentials("bybit", "demo")
            assert k == "dk"
            assert s == "ds"

    def test_binance_demo_empty(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAY_BINANCE_TESTNET_API_KEY", None)
            k, s = _resolve_credentials("binance", "demo")
            assert k == ""
            assert s == ""

    def test_binance_dry_run_empty(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            k, s = _resolve_credentials("binance", "dry_run")
            assert k == ""
            assert s == ""


# ---------------------------------------------------------------------------
# from_env: full integration (D1+D2)
# ---------------------------------------------------------------------------


class TestFromEnvIntegration:
    def test_binance_testnet_full(self) -> None:
        env = {
            "CLAY_EXECUTION_MODE": "testnet",
            "CLAY_EXECUTION_VENUE": "binance",
            "CLAY_BINANCE_TESTNET_API_KEY": "k",
            "CLAY_BINANCE_TESTNET_API_SECRET": "s",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = ExecutionConfig.from_env()
            assert cfg.mode == "testnet"
            assert cfg.venue == "binance"
            assert cfg.api_key == "k"
            assert cfg.api_secret == "s"

    def test_bybit_demo_full(self) -> None:
        env = {
            "CLAY_EXECUTION_MODE": "demo",
            "CLAY_EXECUTION_VENUE": "bybit",
            "CLAY_BYBIT_DEMO_API_KEY": "dk",
            "CLAY_BYBIT_DEMO_API_SECRET": "ds",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = ExecutionConfig.from_env()
            assert cfg.mode == "demo"
            assert cfg.venue == "bybit"
            assert cfg.api_key == "dk"
            assert cfg.api_secret == "ds"

    def test_exchange_id_unaffected(self) -> None:
        env = {
            "CLAY_EXECUTION_VENUE": "bybit",
            "CLAY_EXECUTION_EXCHANGE_ID": "bybit_spot",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = ExecutionConfig.from_env()
            assert cfg.exchange_id == "bybit_spot"
            assert cfg.venue == "bybit"


# ---------------------------------------------------------------------------
# _build_execution_client (D3)
# ---------------------------------------------------------------------------


class TestBuildExecutionClient:
    """Tests for _build_execution_client — venue × mode × creds matrix."""

    def test_binance_testnet_builds(self) -> None:
        from clay.bootstrap import _build_execution_client

        env = {
            "CLAY_EXECUTION_MODE": "testnet",
            "CLAY_EXECUTION_VENUE": "binance",
            "CLAY_BINANCE_TESTNET_API_KEY": "k",
            "CLAY_BINANCE_TESTNET_API_SECRET": "s",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = ExecutionConfig.from_env()
            gate = _build_execution_client(cfg)
            assert gate is not None
            # Unwrap: ExecutionProofGate._inner → ResilientExecutionAdapter._inner → BinanceExecutionAdapter
            resilient = gate._inner
            adapter = resilient._inner
            assert isinstance(adapter, BinanceExecutionAdapter)
            assert adapter.environment == Environment.TESTNET

    def test_bybit_testnet_builds(self) -> None:
        from clay.bootstrap import _build_execution_client

        env = {
            "CLAY_EXECUTION_MODE": "testnet",
            "CLAY_EXECUTION_VENUE": "bybit",
            "CLAY_BYBIT_TESTNET_API_KEY": "k",
            "CLAY_BYBIT_TESTNET_API_SECRET": "s",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = ExecutionConfig.from_env()
            gate = _build_execution_client(cfg)
            assert gate is not None
            adapter = gate._inner._inner
            assert isinstance(adapter, BybitExecutionAdapter)
            assert adapter.environment == Environment.TESTNET

    def test_bybit_demo_builds(self) -> None:
        from clay.bootstrap import _build_execution_client

        env = {
            "CLAY_EXECUTION_MODE": "demo",
            "CLAY_EXECUTION_VENUE": "bybit",
            "CLAY_BYBIT_DEMO_API_KEY": "k",
            "CLAY_BYBIT_DEMO_API_SECRET": "s",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = ExecutionConfig.from_env()
            gate = _build_execution_client(cfg)
            assert gate is not None
            adapter = gate._inner._inner
            assert isinstance(adapter, BybitExecutionAdapter)
            assert adapter.environment == Environment.DEMO

    def test_binance_demo_returns_none(self) -> None:
        from clay.bootstrap import _build_execution_client

        env = {
            "CLAY_EXECUTION_MODE": "demo",
            "CLAY_EXECUTION_VENUE": "binance",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("CLAY_BINANCE_TESTNET_API_KEY", None)
            cfg = ExecutionConfig.from_env()
            assert _build_execution_client(cfg) is None

    def test_dry_run_returns_none(self) -> None:
        from clay.bootstrap import _build_execution_client

        cfg = ExecutionConfig(mode="dry_run", venue="binance")
        assert _build_execution_client(cfg) is None

    def test_unknown_venue_returns_none(self) -> None:
        from clay.bootstrap import _build_execution_client

        cfg = ExecutionConfig(
            mode="testnet", venue="kraken", api_key="k", api_secret="s"
        )
        assert _build_execution_client(cfg) is None

    def test_no_creds_returns_none(self) -> None:
        from clay.bootstrap import _build_execution_client

        cfg = ExecutionConfig(
            mode="testnet", venue="binance", api_key="", api_secret=""
        )
        assert _build_execution_client(cfg) is None


# ---------------------------------------------------------------------------
# Route guard (D4)
# ---------------------------------------------------------------------------


class TestRouteGuard:
    def test_mode_guard_accepts_demo(self) -> None:
        cfg = ExecutionConfig(mode="demo")
        assert cfg.mode in {"testnet", "demo"}

    def test_mode_guard_accepts_testnet(self) -> None:
        cfg = ExecutionConfig(mode="testnet")
        assert cfg.mode in {"testnet", "demo"}

    def test_mode_guard_rejects_dry_run(self) -> None:
        cfg = ExecutionConfig(mode="dry_run")
        assert cfg.mode not in {"testnet", "demo"}


# ---------------------------------------------------------------------------
# Regression: defaults unchanged (D5)
# ---------------------------------------------------------------------------


class TestDefaultsUnchanged:
    def test_default_config_unchanged(self) -> None:
        cfg = ExecutionConfig()
        assert cfg.mode == "dry_run"
        assert cfg.venue == "binance"
        assert cfg.exchange_id == "binance_spot"
        assert cfg.api_key == ""
        assert cfg.api_secret == ""

    def test_from_env_default_builds_nothing(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAY_EXECUTION_MODE", None)
            os.environ.pop("CLAY_EXECUTION_VENUE", None)
            cfg = ExecutionConfig.from_env()
            assert cfg.mode == "dry_run"
            assert cfg.venue == "binance"
            from clay.bootstrap import _build_execution_client

            assert _build_execution_client(cfg) is None
