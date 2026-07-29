"""Guard: no configuration path leads to PRODUCTION trading.

All tests are hermetic — no network, no real keys.
When any test in this file fails, real-money trading is reachable via config.
"""

from __future__ import annotations

import inspect

from clay.execution.config import ExecutionConfig, environment_from_mode

MODES = {"dry_run", "live", "production", "real", "paper", "bogus", ""}


class TestEnvironmentFromModeReturnsNone:
    def test_no_mode_returns_production(self) -> None:
        for mode in MODES:
            assert environment_from_mode(mode) is None, (
                f"environment_from_mode({mode!r}) must return None — "
                f"any non-None return enables real-money trading via config"
            )


class TestNoProductionBranch:
    def test_source_has_no_production_branch(self) -> None:
        source = inspect.getsource(environment_from_mode)
        assert "PRODUCTION" not in source, (
            "environment_from_mode must not contain PRODUCTION — "
            "adding it would make real-money trading reachable via config"
        )


class TestBuildExecutionClientReturnsNone:
    def test_returns_none_when_env_is_none(self) -> None:
        from clay.bootstrap import _build_execution_client

        cfg = ExecutionConfig(mode="dry_run", venue="binance")
        result = _build_execution_client(cfg)
        assert result is None, (
            "must return None when environment_from_mode returns None — "
            "otherwise dry_run builds a live adapter"
        )

    def test_returns_none_when_api_key_empty(self) -> None:
        from clay.bootstrap import _build_execution_client

        cfg = ExecutionConfig(
            mode="testnet", venue="binance", api_key="", api_secret="s"
        )
        result = _build_execution_client(cfg)
        assert result is None, (
            "must return None when api_key is empty — "
            "otherwise missing credentials can reach a live adapter"
        )

    def test_returns_none_when_api_secret_empty(self) -> None:
        from clay.bootstrap import _build_execution_client

        cfg = ExecutionConfig(
            mode="testnet", venue="binance", api_key="k", api_secret=""
        )
        result = _build_execution_client(cfg)
        assert result is None, (
            "must return None when api_secret is empty — "
            "otherwise missing credentials can reach a live adapter"
        )


class TestCommentLock:
    def test_comment_lock_present(self) -> None:
        source = inspect.getsource(environment_from_mode)
        assert "test_no_production_path" in source, (
            "environment_from_mode must contain the comment-lock referencing "
            "test_no_production_path — without it the guard can be silently removed"
        )
