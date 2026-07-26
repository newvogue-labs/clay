"""Проверка политики зависимостей (ADR-039).

Читает pyproject.toml через tomllib и падает, если:
- specifier не имеет верхней границы (нет ни '==', ни '<');
- пакет класса A объявлен не через '=='.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

# ADR-039 §2 — класс A: блокирующие CI-гейты и денежный/венью-путь.
# ruff и ccxt уже == в pyproject, проверяем что НЕ были «разболтаны».
CLASS_A = frozenset({"ruff", "pyright", "pre-commit", "pre-commit-hooks", "ccxt"})

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _load_specifiers() -> dict[str, str]:
    """Вернуть {имя_пакета: specifier} из [project].dependencies и dev."""
    with open(_PYPROJECT, "rb") as f:
        data = tomllib.load(f)

    specs: dict[str, str] = {}

    for raw in data.get("project", {}).get("dependencies", []):
        name, spec = _parse(raw)
        specs[name] = spec

    for raw in data.get("dependency-groups", {}).get("dev", []) or []:
        name, spec = _parse(raw)
        specs[name] = spec

    return specs


def _parse(raw: str) -> tuple[str, str]:
    """Извлечь имя и specifier из строки типа 'pyright==1.1.411'."""
    for op in ("==", ">=", "<=", "~=", "!=", ">", "<"):
        if op in raw:
            idx = raw.index(op)
            return raw[:idx], raw[idx:]
    return raw, ""


class TestDependencyPolicy:
    """ADR-039: каждая зависимость должна иметь верхнюю границу или точный пин."""

    def test_all_specifiers_have_upper_bound(self) -> None:
        specs = _load_specifiers()
        violations: list[str] = []
        for name, spec in sorted(specs.items()):
            if spec and "<" not in spec and "==" not in spec:
                violations.append(f"{name}: {spec}")
        assert not violations, (
            "Следующие specifier-ы без верхней границы (класс C запрещён ADR-039):\n"
            + "\n".join(violations)
        )

    def test_class_a_packages_use_exact_pin(self) -> None:
        specs = _load_specifiers()
        violations: list[str] = []
        for name in sorted(CLASS_A):
            spec = specs.get(name, "")
            if not spec.startswith("=="):
                violations.append(f"{name}: {spec or '(не найден)'}")
        assert not violations, (
            "Пакеты класса A должны быть пиннуты через == (ADR-039 §2):\n"
            + "\n".join(violations)
        )
