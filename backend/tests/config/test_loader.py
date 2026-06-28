from pathlib import Path

import pytest

from clay.config.loader import ConfigLoader


def test_loader_uses_xdg_runtime_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    loader = ConfigLoader()

    assert "clay" in str(loader.paths.config_dir)


def test_invalid_config_rolls_back_to_last_valid_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    loader = ConfigLoader()
    loader.write_default_configs()
    loader.load_all()
    loader.apply_raw_text("runtime", 'mode = "broken"\n')

    with pytest.raises(ValueError):
        loader.load_all()

    restored = loader.restore_last_valid("runtime")

    assert restored.exists()
    assert 'default_state = "background_monitoring"' in restored.read_text(
        encoding="utf-8"
    )
