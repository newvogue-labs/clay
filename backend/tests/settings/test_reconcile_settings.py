"""Tests for D-12c reconcile scheduler settings.

Verifies new env vars are read correctly and defaults are OFF.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from clay.settings.scheduler import SchedulerSettings


class TestReconcileSettingsDefaults:
    """New reconcile settings default to disabled."""

    def test_reconcile_enabled_default_false(self) -> None:
        settings = SchedulerSettings()
        assert settings.reconcile_enabled is False

    def test_reconcile_interval_seconds_default(self) -> None:
        settings = SchedulerSettings()
        assert settings.reconcile_interval_seconds == 300

    def test_reconcile_lookback_seconds_default(self) -> None:
        settings = SchedulerSettings()
        assert settings.reconcile_lookback_seconds == 3600


class TestReconcileSettingsEnvOverride:
    """Env vars override defaults."""

    def test_reconcile_enabled_from_env(self) -> None:
        with patch.dict(os.environ, {"CLAY_SCHEDULER_RECONCILE_ENABLED": "true"}):
            settings = SchedulerSettings()
            assert settings.reconcile_enabled is True

    def test_reconcile_interval_from_env(self) -> None:
        with patch.dict(
            os.environ, {"CLAY_SCHEDULER_RECONCILE_INTERVAL_SECONDS": "600"}
        ):
            settings = SchedulerSettings()
            assert settings.reconcile_interval_seconds == 600

    def test_reconcile_lookback_from_env(self) -> None:
        with patch.dict(
            os.environ, {"CLAY_SCHEDULER_RECONCILE_LOOKBACK_SECONDS": "7200"}
        ):
            settings = SchedulerSettings()
            assert settings.reconcile_lookback_seconds == 7200
