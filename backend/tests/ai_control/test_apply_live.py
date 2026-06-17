from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, patch

import pytest
import httpx

from clay.ai_control.config_reconciler import (
    ConfigReconciler,
    ConfigWriter,
    DeploymentRow,
    ProposedConfig,
    evaluate_pool_health,
)

_LIVE_CONFIG = """\
model_list:
  - model_name: gemini-2.5-flash
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
litellm_settings:
  drop_params: true
router_settings:
  routing_strategy: usage-based-routing-v2
  fallbacks:
    - minimax-m3: [local-ollama]
"""


def _row() -> DeploymentRow:
    return DeploymentRow(
        deployment_id=1, model_name="gemini-2.5-flash",
        upstream_model="gemini/gemini-2.5-flash",
        base_url=None, key_ref="GEMINI_API_KEY",
        key_state="available", params={},
    )


def _different_yaml() -> ProposedConfig:
    return ProposedConfig(document={}, yaml="""\
model_list:
  - model_name: minimax-m3
    litellm_params:
      model: openai/minimaxai/minimax-m3
router_settings:
  strategy: test
""")


def _healthy_resp():
    m = MagicMock(spec=httpx.Response)
    m.status_code = 200
    m.json.return_value = {"status": "healthy", "db": "Not connected"}
    return m


def _unhealthy_resp():
    m = MagicMock(spec=httpx.Response)
    m.status_code = 200
    m.json.return_value = {"status": "unhealthy"}
    return m


@pytest.fixture
def live_path() -> Path:
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(_LIVE_CONFIG)
        path = Path(f.name)
    yield path
    for suffix in ["", ".shadow.yaml", ".yaml.bak"]:
        p = path.with_suffix(suffix) if suffix else path
        if p.exists():
            p.unlink()


@pytest.fixture
def reconciler(live_path: Path) -> ConfigReconciler:
    return ConfigReconciler(live_path)


@pytest.fixture
def writer(reconciler: ConfigReconciler) -> ConfigWriter:
    return ConfigWriter(reconciler)


@pytest.fixture
def proposed(reconciler: ConfigReconciler) -> ProposedConfig:
    return reconciler.render([_row()])


# ── 1. Happy path ────────────────────────────────────────────────────


def _cp_side_effect(*args, **kwargs):
    """subprocess.run side-effect: actually copy file for cp commands."""
    import shutil

    cmd = list(kwargs.get("args") or args[0])
    try:
        cp_idx = cmd.index("cp")
    except ValueError:
        pass
    else:
        src, dst = cmd[cp_idx + 1], cmd[cp_idx + 2]
        shutil.copy2(src, dst)
    return MagicMock(returncode=0)


def test_apply_happy_path(
    writer: ConfigWriter, proposed: ProposedConfig, live_path: Path
) -> None:
    diff_proposed = _different_yaml()

    with (
        patch("subprocess.run", side_effect=_cp_side_effect),
        patch("httpx.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get.return_value = _healthy_resp()

        report = writer.apply_live(diff_proposed, force=True)

    assert report.applied is True
    assert report.backup_path is not None
    assert report.backup_path.exists()
    assert report.restart_ok is True
    assert report.health_ok is True
    assert report.rolled_back is False
    assert report.error is None


def test_apply_happy_path_calls_restart_once(
    writer: ConfigWriter, proposed: ProposedConfig
) -> None:
    diff_proposed = _different_yaml()
    restart_calls: list = []

    def _side_effect(*args, **kwargs):
        cmd = kwargs.get("args") or args[0]
        if "systemctl" in str(cmd):
            restart_calls.append(cmd)
        return MagicMock(returncode=0)

    with (
        patch("subprocess.run", side_effect=_side_effect),
        patch("httpx.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get.return_value = _healthy_resp()
        writer.apply_live(diff_proposed, force=True)

    assert len(restart_calls) == 1


# ── 2. No-op ─────────────────────────────────────────────────────────


def test_apply_noop_skips_when_equivalent(
    writer: ConfigWriter, proposed: ProposedConfig
) -> None:
    write_calls: list = []

    def _side_effect(*args, **kwargs):
        write_calls.append(args)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=_side_effect):
        report = writer.apply_live(proposed)

    assert report.applied is False
    assert report.backup_path is None
    assert report.restart_ok is None
    assert report.health_ok is None
    assert len(write_calls) == 0


def test_apply_noop_can_be_forced(
    writer: ConfigWriter, proposed: ProposedConfig
) -> None:
    with (
        patch("subprocess.run") as mock_run,
        patch("httpx.Client") as mock_client,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        mock_client.return_value.__enter__.return_value.get.return_value = _healthy_resp()
        report = writer.apply_live(proposed, force=True)

    assert report.applied is True


# ── 3. Validation fail ───────────────────────────────────────────────


def test_apply_validation_fail_does_nothing(
    writer: ConfigWriter, proposed: ProposedConfig
) -> None:
    bad = ProposedConfig(document={}, yaml="model_list: []\nrouter_settings:\n  s: v\n")
    write_calls: list = []

    def _side_effect(*args, **kwargs):
        write_calls.append(args)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=_side_effect):
        with pytest.raises(Exception):
            writer.apply_live(bad, force=True)

    assert len(write_calls) == 0


# ── 4. Rollback on unhealthy ─────────────────────────────────────────


def test_apply_rollback_on_unhealthy(
    writer: ConfigWriter, proposed: ProposedConfig
) -> None:
    diff_proposed = _different_yaml()
    restart_calls: list = []

    def _side_effect(*args, **kwargs):
        cmd = list(kwargs.get("args") or args[0])
        if "systemctl" in str(cmd):
            restart_calls.append(cmd)
        return MagicMock(returncode=0)

    with (
        patch("subprocess.run", side_effect=_side_effect),
        patch("httpx.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get.return_value = _unhealthy_resp()
        report = writer.apply_live(diff_proposed, force=True, health_timeout=0.5, health_interval=0.1)

    assert report.applied is True
    assert report.restart_ok is True
    assert report.health_ok is False
    assert report.rolled_back is True
    assert report.error is not None
    assert "health" in str(report.error).lower()
    assert len(restart_calls) == 2  # initial + rollback


# ── 5. Rollback on restart fail ──────────────────────────────────────


def test_apply_rollback_on_restart_fail(
    writer: ConfigWriter, proposed: ProposedConfig
) -> None:
    diff_proposed = _different_yaml()

    def _fail_restart(*args, **kwargs):
        cmd = list(kwargs.get("args") or args[0])
        if "systemctl" in str(cmd):
            raise subprocess.CalledProcessError(1, cmd)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=_fail_restart):
        report = writer.apply_live(diff_proposed, force=True)

    assert report.applied is True
    assert report.restart_ok is False
    assert report.health_ok is False
    assert report.rolled_back is True
    assert "restart" in str(report.error).lower()


# ── 6. Health-parse: db:Not connected is healthy ─────────────────────


def test_apply_health_parse_db_not_connected_is_healthy(
    writer: ConfigWriter, proposed: ProposedConfig
) -> None:
    diff_proposed = _different_yaml()

    with (
        patch("subprocess.run") as mock_run,
        patch("httpx.Client") as mock_client,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        mock_client.return_value.__enter__.return_value.get.return_value = _healthy_resp()

        report = writer.apply_live(diff_proposed, force=True)

    assert report.health_ok is True


# ── 7. File write is called with correct args ────────────────────────


def test_apply_writes_via_sudo_as_clay(
    writer: ConfigWriter, proposed: ProposedConfig
) -> None:
    diff_proposed = _different_yaml()
    cmds: list[list[str]] = []

    def _record(*args, **kwargs):
        cmd = list(kwargs.get("args") or args[0])
        cmds.append(cmd)
        return MagicMock(returncode=0)

    with (
        patch("subprocess.run", side_effect=_record),
        patch("httpx.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get.return_value = _healthy_resp()
        writer.apply_live(diff_proposed, force=True)

    cp_cmds = [c for c in cmds if "cp" in c]
    chmod_cmds = [c for c in cmds if "chmod" in c]
    assert any("-u" in c and "clay" in c for c in cp_cmds)
    assert any("640" in str(c) for c in chmod_cmds)
    assert any("systemctl" in c for c in cmds)


# ── 8. No os.kill calls ──────────────────────────────────────────────


def test_apply_no_os_kill(
    writer: ConfigWriter, proposed: ProposedConfig
) -> None:
    diff_proposed = _different_yaml()
    kill_calls: list = []

    def _guard_kill(*args, **kwargs):
        kill_calls.append((args, kwargs))
        return None

    with (
        patch("subprocess.run") as mock_run,
        patch("httpx.Client") as mock_client,
        patch("os.kill", _guard_kill),
    ):
        mock_run.return_value = MagicMock(returncode=0)
        mock_client.return_value.__enter__.return_value.get.return_value = _healthy_resp()
        writer.apply_live(diff_proposed, force=True)

    assert len(kill_calls) == 0


# ── S3c-3: degraded-mode ──────────────────────────────────────────


class TestEvaluatePoolHealth:
    """evaluate_pool_health() — pure logic, 0 mocks."""

    def test_zero_rows_is_degraded(self) -> None:
        health = evaluate_pool_health([])
        assert health.degraded is True
        assert health.available_total == 0
        assert health.floor == 1

    def test_below_floor_is_degraded(self) -> None:
        rows = [_row()]
        health = evaluate_pool_health(rows, floor=2)
        assert health.degraded is True
        assert health.available_total == 1

    def test_exactly_floor_is_healthy(self) -> None:
        rows = [_row()]
        health = evaluate_pool_health(rows, floor=1)
        assert health.degraded is False
        assert health.available_total == 1

    def test_partial_model_name_not_degraded(self) -> None:
        r1 = _row()  # model_name="gemini-2.5-flash"
        r2 = DeploymentRow(
            deployment_id=2, model_name="minimax-m3",
            upstream_model="openai/minimaxai/minimax-m3",
            base_url=None, key_ref="NVIDIA_API_KEY",
            key_state="available", params={},
        )
        health = evaluate_pool_health([r1, r2], floor=1)
        assert health.degraded is False
        assert health.available_total == 2
        assert health.by_model_name == {"gemini-2.5-flash": 1, "minimax-m3": 1}

    def test_counts_by_model_name(self) -> None:
        r1 = _row()
        r2 = _row()  # same model_name (e.g. 2 providers for one model)
        health = evaluate_pool_health([r1, r2])
        assert health.by_model_name == {"gemini-2.5-flash": 2}


class TestReconcileDegraded:
    """ConfigWriter.reconcile() — degraded branch via mocks."""

    def test_zero_available_degraded(
        self, writer: ConfigWriter,
    ) -> None:
        subprocess_calls: list = []

        def _guard(*args, **kwargs):
            subprocess_calls.append(args)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=_guard):
            report = writer.reconcile([], force=True)

        assert report.status == "degraded"
        assert report.applied is False
        assert report.available_total == 0
        assert "degraded" in (report.error or "").lower()
        assert len(subprocess_calls) == 0  # no write, no restart

    def test_below_floor_degraded(
        self, writer: ConfigWriter,
    ) -> None:
        rows = [_row()]  # 1 available, floor=2
        subprocess_calls: list = []

        def _guard(*args, **kwargs):
            subprocess_calls.append(args)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=_guard):
            report = writer.reconcile(rows, floor=2, force=True)

        assert report.status == "degraded"
        assert report.available_total == 1
        assert len(subprocess_calls) == 0

    def test_healthy_applies(
        self, writer: ConfigWriter,
    ) -> None:
        rows = [_row()]
        with (
            patch("subprocess.run") as mock_run,
            patch("httpx.Client") as mock_client,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            mock_client.return_value.__enter__.return_value.get.return_value = _healthy_resp()
            report = writer.reconcile(rows, force=True)

        assert report.status == "applied"
        assert report.applied is True
        assert report.restart_ok is True
        assert report.health_ok is True
        assert report.available_total == 1

    def test_rolled_back(
        self, writer: ConfigWriter,
    ) -> None:
        rows = [_row()]
        with (
            patch("subprocess.run") as mock_run,
            patch("httpx.Client") as mock_client,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            mock_client.return_value.__enter__.return_value.get.return_value = _unhealthy_resp()
            report = writer.reconcile(
                rows, force=True, health_timeout=0.5, health_interval=0.1,
            )

        assert report.status == "rolled_back"
        assert report.rolled_back is True

    def test_noop_when_equivalent(
        self, writer: ConfigWriter, proposed: ProposedConfig,
    ) -> None:
        rows = [_row()]
        subprocess_calls: list = []

        def _guard(*args, **kwargs):
            subprocess_calls.append(args)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=_guard):
            report = writer.reconcile(rows)

        assert report.status == "noop"
        assert report.applied is False
        assert len(subprocess_calls) == 0

    def test_degraded_never_raises(
        self, writer: ConfigWriter,
    ) -> None:
        """reconcile() never raises on degraded — returns status."""
        report = writer.reconcile([])
        assert report.status == "degraded"

    def test_classification_degraded_vs_validation(
        self, writer: ConfigWriter,
    ) -> None:
        """0 rows → degraded; malformed (after render) → fails.

        In reconcile, empty render (0 rows) hits degraded branch before
        validate — verify it's NOT mis-classified as 'failed'.
        """
        report = writer.reconcile([], force=True)
        assert report.status == "degraded"
        assert "degraded" in (report.error or "").lower()
