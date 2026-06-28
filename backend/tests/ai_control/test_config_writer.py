from __future__ import annotations

import stat
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

import pytest

from clay.ai_control.config_reconciler import (
    ConfigReconciler,
    ConfigValidationError,
    ConfigWriter,
    DeploymentRow,
    ProposedConfig,
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


def _row(
    model_name: str = "gemini-2.5-flash",
    upstream_model: str = "gemini/gemini-2.5-flash",
    base_url: str | None = None,
    key_ref: str | None = "GEMINI_API_KEY",
    key_state: str | None = "available",
    params: dict | None = None,
) -> DeploymentRow:
    return DeploymentRow(
        deployment_id=1,
        model_name=model_name,
        upstream_model=upstream_model,
        base_url=base_url,
        key_ref=key_ref,
        key_state=key_state,
        params=params or {},
    )


@pytest.fixture
def live_path() -> Path:
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(_LIVE_CONFIG)
        path = Path(f.name)
    yield path
    for p in [path, path.with_suffix(".shadow.yaml"), path.with_suffix(".yaml.bak")]:
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


def _make_proposed(yaml_str: str) -> ProposedConfig:
    return ProposedConfig(document={}, yaml=yaml_str)


# ── Validation ───────────────────────────────────────────────────────


def test_validate_passes(live_path: Path) -> None:
    ConfigWriter.validate(_make_proposed(_LIVE_CONFIG))


def test_validate_empty_yaml(writer: ConfigWriter) -> None:
    with pytest.raises(ConfigValidationError, match="empty"):
        writer.validate(_make_proposed(""))


def test_validate_empty_model_list(writer: ConfigWriter) -> None:
    yaml = "model_list: []\nrouter_settings:\n  strategy: test\n"
    with pytest.raises(ConfigValidationError, match="non-empty"):
        writer.validate(_make_proposed(yaml))


def test_validate_missing_model_name(writer: ConfigWriter) -> None:
    yaml = """\
model_list:
  - litellm_params:
      model: test/model
router_settings:
  strategy: test
"""
    with pytest.raises(ConfigValidationError, match="model_name"):
        writer.validate(_make_proposed(yaml))


def test_validate_missing_model_param(writer: ConfigWriter) -> None:
    yaml = """\
model_list:
  - model_name: test
    litellm_params: {}
router_settings:
  strategy: test
"""
    with pytest.raises(ConfigValidationError, match="litellm_params.model"):
        writer.validate(_make_proposed(yaml))


def test_validate_missing_router_settings(writer: ConfigWriter) -> None:
    yaml = """\
model_list:
  - model_name: test
    litellm_params:
      model: test/model
"""
    with pytest.raises(ConfigValidationError, match="router_settings"):
        writer.validate(_make_proposed(yaml))


# ── Atomic write ─────────────────────────────────────────────────────


def test_write_shadow_creates_file(
    writer: ConfigWriter, proposed: ProposedConfig, live_path: Path
) -> None:
    shadow = live_path.with_suffix(".shadow.yaml")
    result = writer.write_shadow(proposed)

    assert result == shadow
    assert shadow.exists()
    assert shadow.stat().st_size > 0


def test_write_shadow_content_matches(
    writer: ConfigWriter, proposed: ProposedConfig, live_path: Path
) -> None:
    writer.write_shadow(proposed)
    shadow = live_path.with_suffix(".shadow.yaml")
    content = shadow.read_text()
    assert content == proposed.yaml


def test_write_shadow_mode_600(
    writer: ConfigWriter, proposed: ProposedConfig, live_path: Path
) -> None:
    writer.write_shadow(proposed)
    shadow = live_path.with_suffix(".shadow.yaml")
    mode = shadow.stat().st_mode & 0o777
    assert mode == (stat.S_IRUSR | stat.S_IWUSR)  # 0600 — tempfile default umask


def test_write_shadow_no_temp_file_left(
    writer: ConfigWriter, proposed: ProposedConfig, live_path: Path
) -> None:
    writer.write_shadow(proposed)
    parent = live_path.parent
    leftovers = [
        p for p in parent.iterdir() if p.suffix == ".tmp" and p.name.startswith("tmp")
    ]
    assert len(leftovers) == 0, f"Temp files left behind: {leftovers}"


def test_write_shadow_custom_path(
    writer: ConfigWriter, proposed: ProposedConfig, tmp_path: Path
) -> None:
    custom = tmp_path / "custom_shadow.yaml"
    result = writer.write_shadow(proposed, shadow_path=custom)
    assert result == custom
    assert custom.exists()


# ── Validation gate (write must fail) ────────────────────────────────


def test_write_fails_on_empty_model_list(writer: ConfigWriter, live_path: Path) -> None:
    bad = _make_proposed("model_list: []\nrouter_settings:\n  s: v\n")
    with pytest.raises(ConfigValidationError):
        writer.write_shadow(bad)
    shadow = live_path.with_suffix(".shadow.yaml")
    assert not shadow.exists()


def test_write_fails_missing_router_settings(
    writer: ConfigWriter, live_path: Path
) -> None:
    bad = _make_proposed(
        "model_list:\n  - model_name: x\n    litellm_params:\n      model: x/m\n"
    )
    with pytest.raises(ConfigValidationError):
        writer.write_shadow(bad)
    shadow = live_path.with_suffix(".shadow.yaml")
    assert not shadow.exists()


# ── Backup ───────────────────────────────────────────────────────────


def test_backup_creates_bak(writer: ConfigWriter, live_path: Path) -> None:
    original = live_path.read_text()
    bak = writer.make_backup()
    assert bak is not None
    assert bak == live_path.with_suffix(".yaml.bak")
    assert bak.exists()
    assert bak.read_text() == original


def test_backup_none_when_no_file(writer: ConfigWriter, tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.yaml"
    bak = writer.make_backup(target=missing)
    assert bak is None


# ── No-op skip ───────────────────────────────────────────────────────


def test_noop_skip_when_shadow_matches(
    writer: ConfigWriter, proposed: ProposedConfig, live_path: Path
) -> None:
    writer.write_shadow(proposed)
    assert writer.noop_skip(proposed) is True


def test_noop_skip_when_shadow_differs(writer: ConfigWriter, live_path: Path) -> None:
    different = _make_proposed(
        "model_list:\n  - model_name: other\n    litellm_params:\n      model: other/m\n"
        "router_settings:\n  strategy: test\n"
    )
    writer.write_shadow(different)
    renderered = _make_proposed(_LIVE_CONFIG)
    assert writer.noop_skip(renderered) is False


def test_noop_skip_no_shadow_yet(
    writer: ConfigWriter, proposed: ProposedConfig, live_path: Path
) -> None:
    assert writer.noop_skip(proposed) is True  # proposed == live → no need to write


# ── Live untouched (guard) ───────────────────────────────────────────


@pytest.mark.parametrize("write_flag", ["w", "wb", "a", "ab"])
def test_live_not_modified(
    writer: ConfigWriter, proposed: ProposedConfig, live_path: Path, write_flag: str
) -> None:
    write_calls: list = []

    original_open = open

    def guarded_open(*args, **kwargs):
        mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")
        path = str(args[0]) if args else ""
        if write_flag in mode and path == str(live_path):
            write_calls.append((args, kwargs))
        return original_open(*args, **kwargs)

    with patch("builtins.open", guarded_open):
        _ = writer.write_shadow(proposed)
        _ = writer.make_backup()

    assert len(write_calls) == 0, f"Live file was written: {write_calls}"


def test_live_not_touched_by_noop_skip(
    writer: ConfigWriter, proposed: ProposedConfig, live_path: Path
) -> None:
    write_calls: list = []

    original_open = open

    def guarded_open(*args, **kwargs):
        mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")
        path = str(args[0]) if args else ""
        if ("w" in mode or "a" in mode or "+" in mode) and path == str(live_path):
            write_calls.append((args, kwargs))
        return original_open(*args, **kwargs)

    with patch("builtins.open", guarded_open):
        writer.write_shadow(proposed)
        assert writer.noop_skip(proposed) is True

    assert len(write_calls) == 0


def test_no_kill_calls(writer: ConfigWriter, proposed: ProposedConfig) -> None:
    kill_calls: list = []

    def guarded_kill(*args, **kwargs):
        kill_calls.append((args, kwargs))
        return None

    with patch("os.kill", guarded_kill):
        writer.write_shadow(proposed)
        writer.make_backup()

    assert len(kill_calls) == 0
