"""Guard: build_xdg_paths трактует пустую XDG_*_HOME как «не задан» (D-64).

Для КАЖДОГО из трёх путей (config_dir / data_dir / cache_dir) обязательны
три ветки охранника:
  (а) переменная задана пустой строкой → дефолт, НЕ относительный ./clay;
  (б) переменная задана непустой → берётся она;
  (в) переменная отсутствует → дефолт.

Образец — охранник D-45 (resolve_audit_journal_path): заданная пустая
строка трактуется как «не задана» (форма ``value or default``, а не
``os.getenv(key, default)``), иначе Path("") увёл бы путь в ./clay.

Hermetic: только локальные tmp-директории, без сети, без ключей.
"""

from __future__ import annotations

import pathlib

from clay.config.paths import build_xdg_paths

_REPO = pathlib.Path(__file__).resolve().parents[3]
_SRC = _REPO / "backend" / "src"

_CASES = [
    ("XDG_CONFIG_HOME", ".config", "config_dir"),
    ("XDG_DATA_HOME", ".local/share", "data_dir"),
    ("XDG_CACHE_HOME", ".cache", "cache_dir"),
]


class TestBuildXdgPaths:
    def test_a_empty_env_falls_back_to_default(self, tmp_path, monkeypatch) -> None:
        """Пустая XDG_*_HOME → дефолт ~/... (не относительный ./clay)."""
        for env_key, default_rel, attr in _CASES:
            home = tmp_path / "home" / env_key
            home.mkdir(parents=True)
            monkeypatch.setenv("HOME", str(home))
            monkeypatch.setenv(env_key, "")

            paths = build_xdg_paths()

            default_base = home / default_rel
            assert paths.__getattribute__(attr) == default_base / "clay", (
                f"{env_key} пуст: ожидался дефолт {default_base / 'clay'}, "
                f"получен {paths.__getattribute__(attr)}"
            )
            assert paths.__getattribute__(attr).is_absolute(), (
                f"{env_key} пуст: путь обязан быть абсолютным (не ./clay)"
            )

    def test_b_set_env_overrides_default(self, tmp_path, monkeypatch) -> None:
        """Непустая XDG_*_HOME → берётся она."""
        for env_key, _default_rel, attr in _CASES:
            xdg = tmp_path / "xdg" / env_key
            home = tmp_path / "home" / env_key
            monkeypatch.setenv("HOME", str(home))
            monkeypatch.setenv(env_key, str(xdg))

            paths = build_xdg_paths()

            assert paths.__getattribute__(attr) == xdg / "clay", (
                f"{env_key} задан: ожидался {xdg / 'clay'}, "
                f"получен {paths.__getattribute__(attr)}"
            )

    def test_c_missing_env_falls_back_to_default(self, tmp_path, monkeypatch) -> None:
        """Отсутствующая XDG_*_HOME → дефолт."""
        for env_key, default_rel, attr in _CASES:
            home = tmp_path / "home" / env_key
            home.mkdir(parents=True)
            monkeypatch.setenv("HOME", str(home))
            monkeypatch.delenv(env_key, raising=False)

            paths = build_xdg_paths()

            default_base = home / default_rel
            assert paths.__getattribute__(attr) == default_base / "clay", (
                f"{env_key} отсутствует: ожидался дефолт {default_base / 'clay'}, "
                f"получен {paths.__getattribute__(attr)}"
            )


class TestSingleXdgResolver:
    def test_no_raw_os_getenv_in_src_paths(self) -> None:
        """Резолв XDG идёт через общий helper, не через os.getenv с дефолтом.

        ``os.getenv("XDG_*_HOME", default)`` возвращает ``""`` для заданной
        пустой переменной → два способа делать одно = долг (D-59). В src
        допускается только вызов ``_xdg_path(key, default)``.
        """
        text = (_SRC / "clay" / "config" / "paths.py").read_text(encoding="utf-8")
        for env_key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            for lineno, line in enumerate(text.splitlines(), 1):
                assert f'os.getenv("{env_key}"' not in line, (
                    f"сырой os.getenv({env_key}) в обход _xdg_path: "
                    f"paths.py:{lineno}: {line}"
                )
        # резолвер единый: и build_xdg_paths, и resolve_audit_journal_path
        # ходят через _xdg_path
        assert "def _xdg_path(" in text
