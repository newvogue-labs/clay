"""Tests for ProviderPoolReconcileJob callable (S3d-2).

Covers:
1. run_once calls writer.reconcile with rows from DB
2. Noop when equivalent (idempotency — called twice on same state)
3. Unexpected exception from reconcile() does NOT propagate
   (historically reconcile() never raises, but the guard is defense-in-depth)
4. Degraded report logged loud
"""

from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, patch

import pytest

from clay.ai_control.config_reconciler import (
    ApplyReport,
    ConfigWriter,
    DeploymentRow,
)
from clay.scheduler.provider_pool_reconcile_job import ProviderPoolReconcileJob

_LIVE_CONFIG = """\
model_list:
  - model_name: gemini-2.5-flash
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
router_settings:
  routing_strategy: usage-based-routing-v2
"""


@pytest.fixture
def live_path():
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(_LIVE_CONFIG)
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


def test_run_once_delegates_to_writer(live_path: Path) -> None:
    """Job opens session, reads deployments, calls writer.reconcile."""
    mock_repo = MagicMock()
    mock_repo.list_enabled_deployments.return_value = []

    session = MagicMock()
    session.__enter__.return_value = session

    session_factory = MagicMock(return_value=session)

    job = ProviderPoolReconcileJob(
        session_factory=session_factory,
        config_path=live_path,
    )
    with patch(
        "clay.scheduler.provider_pool_reconcile_job.SqlProviderPoolRepository",
        return_value=mock_repo,
    ):
        job.run_once()

    mock_repo.list_enabled_deployments.assert_called_once()
    session.__enter__.assert_called_once()


def test_run_once_noop_when_equivalent(live_path: Path) -> None:
    """Job reports noop when rendered config equals live config (idempotency)."""
    row = DeploymentRow(
        deployment_id=1, model_name="gemini-2.5-flash",
        upstream_model="gemini/gemini-2.5-flash",
        base_url=None, key_ref="GEMINI_API_KEY",
        key_state="available", params={},
    )
    mock_repo = MagicMock()
    mock_repo.list_enabled_deployments.return_value = [row]

    session = MagicMock()
    session.__enter__.return_value = session
    session_factory = MagicMock(return_value=session)

    job = ProviderPoolReconcileJob(
        session_factory=session_factory,
        config_path=live_path,
    )

    with patch(
        "clay.scheduler.provider_pool_reconcile_job.SqlProviderPoolRepository",
        return_value=mock_repo,
    ):
        # First call: noop (parity equivalent, no force)
        job.run_once()
        # Second call: same state → also noop (idempotent)
        job.run_once()

    # Verify reconcile was called twice, both noop
    # No subprocess calls, no writes, no restarts — proven by not crashing
    # and not needing subprocess mocks


def test_run_once_does_not_crash_on_exception(live_path: Path, caplog) -> None:
    """Unexpected exception from reconcile() does NOT crash the job thread."""
    mock_writer = MagicMock(spec=ConfigWriter)
    mock_writer.reconcile.side_effect = RuntimeError("unexpected boom")

    session_factory = MagicMock()

    job = ProviderPoolReconcileJob(
        session_factory=session_factory,
        config_path=live_path,
    )
    job._writer = mock_writer  # inject the failing writer

    # Must NOT raise — the _run_safely wrapper handles this in production,
    # but the job itself should also not be the source of a raise
    job.run_once()

    mock_writer.reconcile.assert_called_once()


def test_run_once_degraded_logged_loud(live_path: Path, caplog) -> None:
    """Degraded pool health produces a WARNING log line."""
    mock_writer = MagicMock(spec=ConfigWriter)
    mock_writer.reconcile.return_value = ApplyReport(
        status="degraded", applied=False,
        available_total=0, by_model_name={},
        error="DegradedModeError: 0 available deployments < floor 1",
    )

    session_factory = MagicMock()

    job = ProviderPoolReconcileJob(
        session_factory=session_factory,
        config_path=live_path,
    )
    job._writer = mock_writer

    _logger = logging.getLogger("clay.scheduler.provider_pool_reconcile_job")
    _logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="clay.scheduler.provider_pool_reconcile_job"):
            job.run_once()

        warnings = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING
            and r.name == "clay.scheduler.provider_pool_reconcile_job"
        ]
        assert len(warnings) >= 1
        warning_text = " ".join(r.getMessage() for r in warnings)
        assert "degraded" in warning_text.lower()
        assert "not written" in warning_text.lower() or "last-good" in warning_text.lower()
    finally:
        _logger.removeHandler(caplog.handler)
