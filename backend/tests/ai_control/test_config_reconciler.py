from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

import pytest

from clay.ai_control.config_reconciler import ConfigReconciler, DeploymentRow

# ── Fixtures ─────────────────────────────────────────────────────────

_LIVE_CONFIG = """\
model_list:
  - model_name: gemma4-e2b
    litellm_params:
      model: ollama/gemma4:e2b-it-qat
      api_base: http://127.0.0.1:11434
  - model_name: local-ollama
    litellm_params:
      model: ollama/deepseek-v4-flash:cloud
      api_base: http://127.0.0.1:11434
  - model_name: gemini-2.5-flash
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
  - model_name: minimax-m3
    litellm_params:
      model: openai/minimaxai/minimax-m3
      api_base: https://integrate.api.nvidia.com/v1
      api_key: os.environ/NVIDIA_API_KEY
      rpm: 40
  - model_name: minimax-m2.7
    litellm_params:
      model: openai/minimax-m2.7
      api_base: https://llm.kimchi.dev/openai/v1
      api_key: os.environ/KIMCHI_API_KEY
  - model_name: gemini-3.1-flash-lite
    litellm_params:
      model: gemini/gemini-3.1-flash-lite
      api_key: os.environ/GEMINI_API_KEY
  - model_name: gemma-4-31b
    litellm_params:
      model: gemini/gemma-4-31b-it
      api_key: os.environ/GEMINI_API_KEY

litellm_settings:
  drop_params: true
  telemetry: false

router_settings:
  routing_strategy: usage-based-routing-v2
  cooldown_time: 60
  num_retries: 2
  allowed_fails: 2
  fallbacks:
    - minimax-m3: [minimax-m2.7, local-ollama]
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
def live_config() -> Iterator[Path]:
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(_LIVE_CONFIG)
        path = Path(f.name)
    yield path
    path.unlink()


@pytest.fixture
def seed_rows() -> list[DeploymentRow]:
    return [
        _row(
            model_name="gemma4-e2b",
            upstream_model="ollama/gemma4:e2b-it-qat",
            base_url="http://127.0.0.1:11434",
            key_ref=None,
            key_state=None,
        ),
        _row(
            model_name="local-ollama",
            upstream_model="ollama/deepseek-v4-flash:cloud",
            base_url="http://127.0.0.1:11434",
            key_ref=None,
            key_state=None,
        ),
        _row(
            model_name="gemini-2.5-flash",
            upstream_model="gemini/gemini-2.5-flash",
            base_url=None,
            key_ref="GEMINI_API_KEY",
            key_state="available",
        ),
        _row(
            model_name="gemini-3.1-flash-lite",
            upstream_model="gemini/gemini-3.1-flash-lite",
            base_url=None,
            key_ref="GEMINI_API_KEY",
            key_state="available",
        ),
        _row(
            model_name="gemma-4-31b",
            upstream_model="gemini/gemma-4-31b-it",
            base_url=None,
            key_ref="GEMINI_API_KEY",
            key_state="available",
        ),
        _row(
            model_name="minimax-m3",
            upstream_model="openai/minimaxai/minimax-m3",
            base_url="https://integrate.api.nvidia.com/v1",
            key_ref="NVIDIA_API_KEY",
            key_state="available",
            params={"rpm": 40},
        ),
        _row(
            model_name="minimax-m2.7",
            upstream_model="openai/minimax-m2.7",
            base_url="https://llm.kimchi.dev/openai/v1",
            key_ref="KIMCHI_API_KEY",
            key_state="available",
        ),
    ]


# ── 1. Unit render ───────────────────────────────────────────────────


def test_render_maps_all_seven_deployments(
    live_config: Path, seed_rows: list[DeploymentRow]
) -> None:
    reconciler = ConfigReconciler(live_config)
    proposed = reconciler.render(seed_rows)

    data = reconciler._parse_semantic_str(proposed.yaml)
    models = data["model_index"]

    assert len(models) == 7
    assert ("gemma4-e2b", "ollama/gemma4:e2b-it-qat") in models
    assert ("local-ollama", "ollama/deepseek-v4-flash:cloud") in models
    assert ("gemini-2.5-flash", "gemini/gemini-2.5-flash") in models
    assert ("gemini-3.1-flash-lite", "gemini/gemini-3.1-flash-lite") in models
    assert ("gemma-4-31b", "gemini/gemma-4-31b-it") in models
    assert ("minimax-m3", "openai/minimaxai/minimax-m3") in models
    assert ("minimax-m2.7", "openai/minimax-m2.7") in models


def test_render_keyless_omits_api_key(live_config: Path) -> None:
    reconciler = ConfigReconciler(live_config)
    proposed = reconciler.render([_row(key_ref=None, key_state=None)])
    data = reconciler._parse_semantic_str(proposed.yaml)
    key = ("test-model", "gemini/gemini-2.5-flash")
    lp = data["model_index"].get(key, {})
    assert "api_key" not in lp


def test_render_keyless_omits_api_base(live_config: Path) -> None:
    reconciler = ConfigReconciler(live_config)
    proposed = reconciler.render([_row(base_url=None, key_ref=None, key_state=None)])
    data = reconciler._parse_semantic_str(proposed.yaml)
    key = ("test-model", "gemini/gemini-2.5-flash")
    lp = data["model_index"].get(key, {})
    assert "api_base" not in lp


def test_render_inlines_extra_params(live_config: Path) -> None:
    reconciler = ConfigReconciler(live_config)
    proposed = reconciler.render(
        [
            _row(
                model_name="minimax-m3",
                upstream_model="openai/minimaxai/minimax-m3",
                key_ref="NVIDIA_API_KEY",
                params={"rpm": 40},
            )
        ]
    )
    data = reconciler._parse_semantic_str(proposed.yaml)
    key = ("minimax-m3", "openai/minimaxai/minimax-m3")
    lp = data["model_index"].get(key, {})
    assert lp.get("rpm") == 40


def test_render_preserves_existing_sections(
    live_config: Path, seed_rows: list[DeploymentRow]
) -> None:
    reconciler = ConfigReconciler(live_config)
    proposed = reconciler.render(seed_rows)

    data = reconciler._parse_semantic_str(proposed.yaml)
    rest = data["rest"]

    assert rest.get("litellm_settings") == {"drop_params": True, "telemetry": False}
    assert (
        rest.get("router_settings", {}).get("routing_strategy")
        == "usage-based-routing-v2"
    )


# ── 2. Parity no-op (GATE) ───────────────────────────────────────────


def test_parity_no_op_with_seed_data(
    live_config: Path, seed_rows: list[DeploymentRow]
) -> None:
    reconciler = ConfigReconciler(live_config)
    proposed = reconciler.render(seed_rows)
    report = reconciler.diff(proposed.yaml)

    assert report.is_equivalent, (
        f"Parity check FAILED: added={report.added}, removed={report.removed}, changed={report.changed}"
    )
    assert len(report.added) == 0
    assert len(report.removed) == 0
    assert len(report.changed) == 0


# ── 3. Exclusion ─────────────────────────────────────────────────────


def test_excludes_cooling_deployment(
    live_config: Path, seed_rows: list[DeploymentRow]
) -> None:
    for row in seed_rows:
        if row.model_name == "minimax-m3":
            row.key_state = "cooling"
            break

    reconciler = ConfigReconciler(live_config)
    proposed = reconciler.render(seed_rows)
    report = reconciler.diff(proposed.yaml)

    assert not report.is_equivalent
    assert ("minimax-m3", "openai/minimaxai/minimax-m3") in report.removed


def test_excludes_exhausted_deployment(
    live_config: Path, seed_rows: list[DeploymentRow]
) -> None:
    for row in seed_rows:
        if row.model_name == "gemini-2.5-flash":
            row.key_state = "exhausted"
            break

    reconciler = ConfigReconciler(live_config)
    proposed = reconciler.render(seed_rows)
    report = reconciler.diff(proposed.yaml)

    assert not report.is_equivalent
    assert ("gemini-2.5-flash", "gemini/gemini-2.5-flash") in report.removed


def test_excludes_dead_deployment(
    live_config: Path, seed_rows: list[DeploymentRow]
) -> None:
    for row in seed_rows:
        if row.model_name == "minimax-m2.7":
            row.key_state = "dead"
            break

    reconciler = ConfigReconciler(live_config)
    proposed = reconciler.render(seed_rows)
    report = reconciler.diff(proposed.yaml)

    assert not report.is_equivalent
    assert ("minimax-m2.7", "openai/minimax-m2.7") in report.removed


# ── 4. Guard: no disk writes ─────────────────────────────────────────


@pytest.mark.parametrize("write_flag", ["w", "wb", "a", "ab"])
def test_guard_no_file_write(
    live_config: Path, seed_rows: list[DeploymentRow], write_flag: str
) -> None:
    write_calls: list[tuple] = []

    original_open = open

    def guarded_open(*args, **kwargs):
        mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")
        if "w" in mode or "a" in mode or "+" in mode:
            write_calls.append((args, kwargs))
        return original_open(*args, **kwargs)

    with patch("builtins.open", guarded_open):
        reconciler = ConfigReconciler(live_config)
        proposed = reconciler.render(seed_rows)
        report = reconciler.diff(proposed.yaml)

    assert report.is_equivalent
    assert len(write_calls) == 0, f"Unexpected write calls: {write_calls}"


def test_guard_no_os_kill(live_config: Path, seed_rows: list[DeploymentRow]) -> None:
    kill_calls: list[tuple] = []

    def guarded_kill(*args, **kwargs):
        kill_calls.append((args, kwargs))
        return None

    with patch("os.kill", guarded_kill):
        reconciler = ConfigReconciler(live_config)
        proposed = reconciler.render(seed_rows)
        report = reconciler.diff(proposed.yaml)

    assert report.is_equivalent
    assert len(kill_calls) == 0, f"Unexpected os.kill calls: {kill_calls}"
