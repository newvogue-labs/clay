"""Guard: гигиена pytest-маркеров (D-65).

Обязательные ветки:
  (а) каждый используемый в tests/ кастомный маркер объявлен в
      ``[tool.pytest.ini_options].markers`` (pyproject.toml) — иначе при
      включённом ``--strict-markers`` тест упадёт с "unregistered mark";
  (б) каждый объявленный маркер реально используется в tests/ —
      «сирота» = мёртвый конфиг (D-59: два способа делать одно = долг).

Системные/плагинные маркеры (parametrize, skip, skipif, xfail,
filterwarnings, usefixtures, tryfirst, trylast, anyio, asyncio,
hypothesis) регистрируются самим pytest или его плагинами и объявлять их
в pyproject не нужно — они в whitelist'е ниже.

Hermetic: читает только файлы репозитория, без сети, без ключей.
"""

from __future__ import annotations

import pathlib
import re

_REPO = pathlib.Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_PYPROJECT = _BACKEND / "pyproject.toml"
_TESTS = _BACKEND / "tests"

# Маркеры, регистрируемые самим pytest или подключёнными плагинами
# (pytest-anyio, pytest-asyncio, hypothesis) — в pyproject объявлять не нужно.
_PLUGIN_MARKERS = frozenset(
    {
        "parametrize",
        "skip",
        "skipif",
        "xfail",
        "filterwarnings",
        "usefixtures",
        "tryfirst",
        "trylast",
        "anyio",
        "asyncio",
        "hypothesis",
    }
)

_MARK_DECL_RE = re.compile(r'"(\w+):')
_MARK_USE_RE = re.compile(r"@pytest\.mark\.(\w+)")


def _declared_markers() -> set[str]:
    """Имена маркеров из секции ``markers = [...]`` pyproject.toml."""
    text = _PYPROJECT.read_text(encoding="utf-8")
    section = text.split("markers = [", 1)[1].split("]", 1)[0]
    return set(_MARK_DECL_RE.findall(section))


def _used_markers() -> set[str]:
    """Все имена маркеров, встречающиеся в ``@pytest.mark.*`` в tests/."""
    used: set[str] = set()
    for path in sorted(_TESTS.rglob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            used.update(_MARK_USE_RE.findall(line))
    return used


class TestMarkerHygiene:
    def test_a_used_custom_markers_are_declared(self) -> None:
        declared = _declared_markers()
        undeclared = sorted((_used_markers() - _PLUGIN_MARKERS) - declared)
        assert not undeclared, (
            "маркер используется в tests/, но не объявлен в pyproject.toml "
            f"markers (при --strict-markers упадёт unregistered mark): {undeclared}"
        )

    def test_b_declared_markers_are_used(self) -> None:
        orphans = sorted(_declared_markers() - _used_markers())
        assert not orphans, (
            "маркер объявлен в pyproject.toml, но нигде не используется "
            f"(сирота — мёртвый конфиг): {orphans}"
        )
