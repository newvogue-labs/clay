"""Tests for ExecutionConfig.order_ledger_enabled flag."""

from __future__ import annotations

import os
from unittest.mock import patch

from clay.execution.config import ExecutionConfig


class TestOrderLedgerEnabled:
    def test_default_false(self) -> None:
        cfg = ExecutionConfig()
        assert cfg.order_ledger_enabled is False

    def test_from_env_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAY_ORDER_LEDGER_ENABLED", None)
            cfg = ExecutionConfig.from_env()
            assert cfg.order_ledger_enabled is False

    def test_from_env_true_string(self) -> None:
        with patch.dict(os.environ, {"CLAY_ORDER_LEDGER_ENABLED": "true"}):
            cfg = ExecutionConfig.from_env()
            assert cfg.order_ledger_enabled is True

    def test_from_env_one_string(self) -> None:
        with patch.dict(os.environ, {"CLAY_ORDER_LEDGER_ENABLED": "1"}):
            cfg = ExecutionConfig.from_env()
            assert cfg.order_ledger_enabled is True

    def test_from_env_false_string(self) -> None:
        with patch.dict(os.environ, {"CLAY_ORDER_LEDGER_ENABLED": "0"}):
            cfg = ExecutionConfig.from_env()
            assert cfg.order_ledger_enabled is False

    def test_from_env_random_string(self) -> None:
        with patch.dict(os.environ, {"CLAY_ORDER_LEDGER_ENABLED": "yes"}):
            cfg = ExecutionConfig.from_env()
            assert cfg.order_ledger_enabled is False
