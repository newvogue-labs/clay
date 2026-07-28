"""Языковая гигиена дерева (ADR-039, D-33).

Сканирует радиус: backend/src, backend/tests, backend/scripts, docs,
frontend/src, .github на присутствие символов CJK-класса.

Регулярное выражение — константа модуля, один источник истины.
Allowlist/исключений нет. Нарушение = падение с перечислением
путь:строка каждого попадания.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]

# Один источник истины для класса символов CJK.
_CJK_RE = re.compile(
    r"[\u2e80-\u2fff"
    r"\u3000-\u303f"
    r"\u3040-\u30ff"
    r"\u3400-\u4dbf"
    r"\u4e00-\u9fff"
    r"\uf900-\ufaff"
    r"\uff00-\uffef]"
)

_ROOTS = [
    _REPO / "backend" / "src",
    _REPO / "backend" / "tests",
    _REPO / "backend" / "scripts",
    _REPO / "docs",
    _REPO / "frontend" / "src",
    _REPO / ".github",
]

_EXTS = {
    ".py",
    ".md",
    ".ts",
    ".tsx",
    ".yml",
    ".yaml",
    ".toml",
    ".json",
    ".sql",
}


def _scan_cjk() -> list[str]:
    """Сканировать радиус и вернуть список 'путь:строка' с CJK-символами."""
    hits: list[str] = []
    for root in _ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in _EXTS:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if _CJK_RE.search(line):
                    rel = path.relative_to(_REPO)
                    hits.append(f"{rel}:{i}")
    return hits


class TestSourceHygiene:
    """Дерево не содержит CJK-символов (D-33)."""

    def test_no_cjk_characters(self) -> None:
        hits = _scan_cjk()
        assert not hits, f"Найдены CJK-символы в {len(hits)} строках:\n" + "\n".join(
            hits
        )
