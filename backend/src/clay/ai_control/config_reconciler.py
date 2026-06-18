from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Sequence

from ruamel.yaml import YAML

from clay.ai_control.provider_pool import DeploymentRow


logger = logging.getLogger(__name__)

_AVAILABLE = "available"
_KEY_PREFIX = "os.environ/"
_SHADOW_SUFFIX = ".shadow.yaml"
_BACKUP_SUFFIX = ".yaml.bak"


class ConfigValidationError(Exception):
    """Raised when a proposed config fails pre-write validation."""


class DegradedModeError(Exception):
    """Raised when pool health drops below floor — config NOT written."""


@dataclass
class ProposedConfig:
    document: dict
    yaml: str


@dataclass
class ParityReport:
    is_equivalent: bool
    added: list[tuple[str, str]] = field(default_factory=list)
    removed: list[tuple[str, str]] = field(default_factory=list)
    changed: list[tuple[str, str, dict, dict]] = field(default_factory=list)


@dataclass
class PoolHealth:
    """Health snapshot of a provider-pool render result."""

    available_total: int
    by_model_name: dict[str, int]
    degraded: bool
    floor: int


def evaluate_pool_health(
    rows: Sequence[DeploymentRow],
    floor: int = 1,
) -> PoolHealth:
    """Assess whether the pool has enough healthy deployments to render.

    ``rows`` should be *already filtered to available* (see
    ``_filter_available``).  ``floor`` is the minimum number of
    deployments required to avoid a degraded state (default **1**).
    """
    by_model_name: dict[str, int] = {}
    for r in rows:
        by_model_name[r.model_name] = by_model_name.get(r.model_name, 0) + 1
    available_total = len(rows)
    return PoolHealth(
        available_total=available_total,
        by_model_name=by_model_name,
        degraded=available_total < floor,
        floor=floor,
    )


class ConfigReconciler:
    """Reconciles provider_deployments from the database against the
    live LiteLLM ``config.yaml``.

    Core render/diff — *read-only*. Writing is delegated to
    ``ConfigWriter``.
    """

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.indent(mapping=2, sequence=4, offset=2)

    def render(self, rows: Sequence[DeploymentRow]) -> ProposedConfig:
        available = self._filter_available(rows)
        model_list = [self._row_to_entry(r) for r in available]

        doc = self._load_round_trip()
        doc["model_list"] = model_list

        buf = StringIO()
        self._yaml.dump(doc, buf)
        return ProposedConfig(document=doc, yaml=buf.getvalue())

    def diff(self, proposed_yaml: str) -> ParityReport:
        return self.diff_yaml(proposed_yaml, self._config_path)

    def diff_yaml(self, proposed_yaml: str, current_path: Path) -> ParityReport:
        live = self._parse_semantic(current_path)
        prop = self._parse_semantic_str(proposed_yaml)

        live_models = set(live["model_index"])
        prop_models = set(prop["model_index"])

        added = sorted(prop_models - live_models)
        removed = sorted(live_models - prop_models)
        common = live_models & prop_models
        changed: list[tuple[str, str, dict, dict]] = []
        for key in sorted(common):
            if live["model_index"][key] != prop["model_index"][key]:
                changed.append((*key, live["model_index"][key], prop["model_index"][key]))

        rest_equal = live["rest"] == prop["rest"]

        return ParityReport(
            is_equivalent=(not added and not removed and not changed and rest_equal),
            added=added,
            removed=removed,
            changed=changed,
        )

    def _filter_available(self, rows: Sequence[DeploymentRow]) -> list[DeploymentRow]:
        return [r for r in rows if r.key_state is None or r.key_state == _AVAILABLE]

    def _row_to_entry(self, row: DeploymentRow) -> dict:
        lp: dict[str, object] = {"model": row.upstream_model}
        if row.base_url is not None:
            lp["api_base"] = row.base_url
        if row.key_ref is not None:
            lp["api_key"] = f"{_KEY_PREFIX}{row.key_ref}"
        if row.params:
            for k, v in sorted(row.params.items()):
                lp[k] = v
        return {"model_name": row.model_name, "litellm_params": lp}

    def _load_round_trip(self) -> dict:
        with open(self._config_path) as f:
            doc = self._yaml.load(f)
        return doc if doc is not None else {}

    def _parse_semantic(self, path: Path) -> dict:
        with open(path) as f:
            raw = f.read()
        return self._parse_semantic_str(raw)

    @staticmethod
    def _parse_semantic_str(raw: str) -> dict:
        safe = YAML(typ="safe")
        data = safe.load(raw)
        if data is None:
            return {"model_index": {}, "rest": {}}
        model_index: dict[tuple[str, str], dict] = {}
        for entry in data.get("model_list") or []:
            lp = entry.get("litellm_params") or {}
            model = lp.get("model") or ""
            key = (entry["model_name"], str(model))
            canonical = {k: v for k, v in sorted(lp.items()) if v is not None}
            model_index[key] = canonical
        rest = {k: v for k, v in data.items() if k != "model_list"}
        return {"model_index": model_index, "rest": rest}


class ConfigApplyError(Exception):
    """Raised when applying config fails and rollback may have occurred."""


@dataclass
class ApplyReport:
    applied: bool
    backup_path: Path | None = None
    restart_ok: bool | None = None
    health_ok: bool | None = None
    rolled_back: bool = False
    error: str | None = None
    status: str = "noop"
    available_total: int = 0
    by_model_name: dict[str, int] = field(default_factory=dict)


class ConfigWriter:
    """Write-side of configuration management.

    Atomic write + validation + backup + no-op skip + apply_live.
    """

    def __init__(self, reconciler: ConfigReconciler) -> None:
        self._reconciler = reconciler

    @staticmethod
    def validate(proposed: ProposedConfig) -> None:
        safe = YAML(typ="safe")
        data = safe.load(proposed.yaml)
        if data is None:
            raise ConfigValidationError("proposed config is empty (None)")

        model_list = data.get("model_list")
        if not model_list or not isinstance(model_list, list):
            raise ConfigValidationError("model_list must be a non-empty list")

        if len(model_list) < 1:
            raise ConfigValidationError("model_list must have at least one entry")

        if "router_settings" not in data:
            raise ConfigValidationError("proposed config is missing router_settings (round-trip lost data)")

        for i, entry in enumerate(model_list):
            if not entry.get("model_name"):
                raise ConfigValidationError(f"model_list[{i}] missing model_name")
            lp = entry.get("litellm_params") or {}
            if not lp.get("model"):
                raise ConfigValidationError(f"model_list[{i}] litellm_params.model is required")

    def write_shadow(self, proposed: ProposedConfig, shadow_path: Path | None = None) -> Path:
        self.validate(proposed)

        if shadow_path is None:
            shadow_path = self._default_shadow_path()

        parent = shadow_path.parent
        parent.mkdir(parents=True, exist_ok=True)

        with NamedTemporaryFile(mode="w", suffix=".tmp", dir=parent, delete=False) as tmp:
            tmp.write(proposed.yaml)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)

        os.replace(str(tmp_path), str(shadow_path))

        try:
            live_mode = self._reconciler._config_path.stat().st_mode
            shadow_path.chmod(live_mode & 0o777)
        except OSError:
            shadow_path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)

        return shadow_path

    def make_backup(self, target: Path | None = None) -> Path | None:
        if target is None:
            target = self._reconciler._config_path
        if not target.exists():
            return None
        bak = target.with_suffix(_BACKUP_SUFFIX)
        shutil.copy2(str(target), str(bak))
        return bak

    def noop_skip(self, proposed: ProposedConfig, shadow_path: Path | None = None) -> bool:
        if shadow_path is None:
            shadow_path = self._default_shadow_path()
        ref = shadow_path if shadow_path.exists() else self._reconciler._config_path
        report = self._reconciler.diff_yaml(proposed.yaml, ref)
        return report.is_equivalent

    def reconcile(
        self,
        rows: Sequence[DeploymentRow],
        *,
        floor: int = 1,
        force: bool = False,
        health_timeout: float = 15.0,
        health_interval: float = 1.0,
        clay_user: str = "clay",
        sudo_cmd: str = "sudo",
    ) -> ApplyReport:
        """Render, validate, health-check, then apply (or degraded-skip).

        This is the top-level entry point for the reconciliation loop.
        Unlike ``apply_live`` it never raises — errors are captured in
        the returned ``ApplyReport.status``.
        """
        proposed = self._reconciler.render(rows)

        health = evaluate_pool_health(
            self._reconciler._filter_available(rows),
            floor=floor,
        )

        if health.degraded:
            logger.error(
                "DegradedModeError: pool-health degraded — "
                "available_total=%d < floor=%d; by_model_name=%s; "
                "config NOT written, last-good preserved",
                health.available_total, health.floor, health.by_model_name,
            )
            return ApplyReport(
                status="degraded", applied=False,
                available_total=health.available_total,
                by_model_name=health.by_model_name,
                error=(
                    f"DegradedModeError: {health.available_total} available "
                    f"deployments < floor {health.floor}"
                ),
            )

        try:
            self.validate(proposed)
        except ConfigValidationError as e:
            return ApplyReport(
                status="failed", applied=False,
                error=str(e),
                available_total=health.available_total,
                by_model_name=health.by_model_name,
            )

        report = self.apply_live(
            proposed,
            force=force,
            health_timeout=health_timeout,
            health_interval=health_interval,
            clay_user=clay_user,
            sudo_cmd=sudo_cmd,
        )
        report.available_total = health.available_total
        report.by_model_name = health.by_model_name

        if report.applied and report.restart_ok and report.health_ok:
            report.status = "applied"
        elif report.rolled_back:
            report.status = "rolled_back"
        elif report.applied:
            report.status = "failed"
        elif not report.applied and report.error:
            report.status = "failed"
        # else stays "noop"

        return report

    def _install_via_helper(self, shadow_path: Path) -> Path:
        """Call clay-config-install, return backup path from stdout."""
        import subprocess

        r = subprocess.run(
            ["sudo", "/usr/local/sbin/clay-config-install", str(shadow_path)],
            check=True, capture_output=True, text=True,
        )
        return Path(r.stdout.strip())

    def apply_live(
        self,
        proposed: ProposedConfig,
        *,
        force: bool = False,
        health_timeout: float = 15.0,
        health_interval: float = 1.0,
        clay_user: str = "clay",
        sudo_cmd: str = "sudo",
    ) -> ApplyReport:
        self.validate(proposed)
        live = self._reconciler._config_path

        if not force:
            report = self._reconciler.diff_yaml(proposed.yaml, live)
            if report.is_equivalent:
                return ApplyReport(applied=False)

        # Write rendered config to a temp shadow file for the helper
        with NamedTemporaryFile(mode="w", suffix=".yaml", dir="/tmp", delete=False) as tmp:
            tmp.write(proposed.yaml)
            tmp.flush()
            shadow_path = Path(tmp.name)

        try:
            bak = self._install_via_helper(shadow_path)
        except subprocess.CalledProcessError as e:
            return ApplyReport(
                status="failed", applied=False,
                error=f"helper install failed: {e.stderr.strip()}",
            )
        finally:
            shadow_path.unlink(missing_ok=True)

        restart_ok = self._restart_service(sudo_cmd)
        if not restart_ok:
            self._rollback_via_helper(bak)
            return ApplyReport(
                applied=True, backup_path=bak,
                restart_ok=False, health_ok=False,
                rolled_back=True,
                error="restart failed, rolled back to last-good",
            )

        health_ok = self._poll_health(health_timeout, health_interval)
        if not health_ok:
            self._rollback_via_helper(bak)
            return ApplyReport(
                applied=True, backup_path=bak,
                restart_ok=True, health_ok=False,
                rolled_back=True,
                error="health check failed, rolled back to last-good",
            )

        return ApplyReport(
            applied=True, backup_path=bak,
            restart_ok=True, health_ok=True,
        )

    def _rollback_via_helper(self, bak: Path) -> None:
        import subprocess

        try:
            subprocess.run(
                ["sudo", "/usr/local/sbin/clay-config-install", str(bak)],
                check=False, capture_output=True, text=True,
            )
        except Exception:
            pass
        self._restart_service(sudo_cmd="sudo")
        self._poll_health(timeout=15.0, interval=1.0)

    def _restart_service(self, sudo_cmd: str) -> bool:
        import subprocess

        try:
            subprocess.run(
                [sudo_cmd, "systemctl", "restart", "clay-litellm.service"],
                check=True, capture_output=True, text=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def _poll_health(self, timeout: float, interval: float) -> bool:
        import time

        import httpx

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with httpx.Client() as client:
                    r = client.get(
                        "http://127.0.0.1:4000/health/readiness",
                        timeout=max(interval, 3),
                    )
                    if r.status_code == 200:
                        data = r.json()
                        if data.get("status") == "healthy":
                            return True
            except Exception:
                pass
            time.sleep(interval)
        return False

    def _default_shadow_path(self) -> Path:
        return self._reconciler._config_path.with_suffix(_SHADOW_SUFFIX)
