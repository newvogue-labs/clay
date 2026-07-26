"""Согласованность тулчейна: Node/pnpm версии в трёх точках + frozen-режимы (ADR-039).

Проверяет, что .nvmrc, engines в package.json и node-version в CI совпадают,
что packageManager отсутствует, и что frozen-lockfile/locked на месте.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_CI_YML = _REPO / ".github" / "workflows" / "ci.yml"
_NVMRC = _REPO / "frontend" / ".nvmrc"
_PKG_JSON = _REPO / "frontend" / "package.json"
_LOCKFILE = _REPO / "frontend" / "pnpm-lock.yaml"


def _read_ci_node_version() -> str:
    """Извлечь node-version из ci.yml (job frontend)."""
    text = _CI_YML.read_text()
    m = re.search(r"node-version:\s*(\d+)", text)
    assert m, f"node-version не найден в {_CI_YML}"
    return m.group(1)


def _read_ci_pnpm_version() -> str:
    """Извлечь version из pnpm/action-setup в ci.yml."""
    text = _CI_YML.read_text()
    m = re.search(r"pnpm/action-setup@v\d+\s*\n\s+with:\s*\n\s+version:\s*(\d+)", text)
    assert m, f"pnpm version не найден в {_CI_YML}"
    return m.group(1)


def _read_nvmrc_major() -> str:
    """Содержимое .nvmrc (ожидается одно число — major)."""
    return _NVMRC.read_text().strip()


def _read_engines_versions() -> tuple[str, str]:
    """Вернуть (node_lower, pnpm_lower) из engines в package.json."""
    data = json.loads(_PKG_JSON.read_text())
    engines = data.get("engines", {})

    def _major(spec: str) -> str:
        m = re.search(r">=(\d+)", spec)
        assert m, f"major не найден в {spec!r}"
        return m.group(1)

    return _major(engines.get("node", ">=0")), _major(engines.get("pnpm", ">=0"))


class TestNodeConsistency:
    """Node: ci.yml == .nvmrc == package.json engines.node."""

    def test_three_points_agree(self) -> None:
        ci_node = _read_ci_node_version()
        nvmrc = _read_nvmrc_major()
        node_lower, _ = _read_engines_versions()

        assert ci_node == nvmrc == node_lower, (
            f"Node не согласован:\n"
            f"  ci.yml node-version: {ci_node}\n"
            f"  frontend/.nvmrc:     {nvmrc}\n"
            f"  engines.node lower:  {node_lower}"
        )


class TestPnpmConsistency:
    """pnpm: ci.yml action-setup version == package.json engines.pnpm."""

    def test_two_points_agree(self) -> None:
        ci_pnpm = _read_ci_pnpm_version()
        _, pnpm_lower = _read_engines_versions()

        assert ci_pnpm == pnpm_lower, (
            f"pnpm не согласован:\n"
            f"  ci.yml pnpm/action-setup version: {ci_pnpm}\n"
            f"  engines.pnpm lower:               {pnpm_lower}"
        )


class TestNoPackageManager:
    """Поле packageManager отсутствует в frontend/package.json."""

    def test_package_manager_absent(self) -> None:
        data = json.loads(_PKG_JSON.read_text())
        assert "packageManager" not in data, (
            "packageManager найден в package.json — запрещено ADR-039 (corepack-риск в CI)"
        )


class TestFrozenLockfileModes:
    """Frozen-режимы на месте: --locked, --frozen-lockfile, pnpm-lock.yaml существует."""

    def test_ci_has_locked_and_frozen(self) -> None:
        text = _CI_YML.read_text()
        assert "uv sync --locked" in text, "uv sync --locked не найден в ci.yml"
        assert "pnpm install --frozen-lockfile" in text, (
            "pnpm install --frozen-lockfile не найден в ci.yml"
        )

    def test_pnpm_lockfile_exists(self) -> None:
        assert _LOCKFILE.exists(), f"pnpm-lock.yaml не найден: {_LOCKFILE}"
