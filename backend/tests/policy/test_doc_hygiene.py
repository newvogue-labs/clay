"""Гигиена документации и её соответствие коду (D-53, D-55).

Чинящие проверки (G1, G2, G3, G7) охраняют от возврата снятых дрейфов:
уникальность номеров ADR, полнота ADR-индекса, чистота generated-справки
(docs/reference), пути к охранникам с префиксом backend/. Регрессионные
проверки (G4, G5, G6) следят, чтобы канон слоя исполнения
(backend/docs/execution.md) не ссылался на несуществующие тесты,
переменные окружения и миграции.

Allowlist, списки исключений, skip и xfail запрещены: нарушение = падение
с перечислением путь:строка.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]

_ADR_DIR = _REPO / "docs" / "adr"
_REFERENCE_DIR = _REPO / "docs" / "reference"
_CANON = _REPO / "backend" / "docs" / "execution.md"
_SRC_DIR = _REPO / "backend" / "src"
_TESTS_DIR = _REPO / "backend" / "tests"
_MIGRATIONS_DIR = _REPO / "backend" / "alembic" / "versions"

_ENV_TOKEN_RE = re.compile(r"CLAY_[A-Z0-9_]+")


def _is_base_settings(base: ast.expr) -> bool:
    if isinstance(base, ast.Name):
        return base.id == "BaseSettings"
    if isinstance(base, ast.Attribute):
        return base.attr == "BaseSettings"
    return False


def _field_alias(value: ast.expr | None) -> str | None:
    if value is None or not isinstance(value, ast.Call):
        return None
    for kw in value.keywords:
        if kw.arg in {"alias", "validation_alias"} and isinstance(
            kw.value, ast.Constant
        ):
            return str(kw.value.value)
    return None


def _class_env_prefix(node: ast.ClassDef) -> str | None:
    for child in node.body:
        if isinstance(child, ast.AnnAssign):
            target = child.target
            if isinstance(target, ast.Name) and target.id == "model_config":
                return _env_prefix_from_value(child.value)
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name) and target.id == "model_config":
                    return _env_prefix_from_value(child.value)
    return None


def _env_prefix_from_value(value: ast.expr | None) -> str | None:
    if isinstance(value, ast.Call):
        for kw in value.keywords:
            if kw.arg == "env_prefix" and isinstance(kw.value, ast.Constant):
                return str(kw.value.value)
        if value.args and isinstance(value.args[0], ast.Constant):
            return str(value.args[0].value)
    if isinstance(value, ast.Dict):
        for key, val in zip(value.keys, value.values):
            if isinstance(key, ast.Constant) and key.value == "env_prefix":
                if isinstance(val, ast.Constant):
                    return str(val.value)
    return None


def _pydantic_generated_env_names(tree: ast.AST) -> set[str]:
    """Имена env-переменных, генерируемые pydantic-settings (AST).

    Для каждого класса-наследника BaseSettings: env_prefix из model_config
    и каждое объявленное поле класса → имя ``prefix.upper() + field.upper()``.
    Явный ``alias``/``validation_alias`` поля добавляется отдельно.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(_is_base_settings(base) for base in node.bases):
            continue
        prefix = _class_env_prefix(node)
        if prefix is None:
            continue
        prefix_upper = prefix.upper()
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                field = child.target.id
                names.add(f"{prefix_upper}{field.upper()}")
                alias = _field_alias(child.value)
                if alias:
                    names.add(alias.upper())
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        names.add(f"{prefix_upper}{target.id.upper()}")
                        alias = _field_alias(child.value)
                        if alias:
                            names.add(alias.upper())
    return names


def _runtime_env_names(repo: Path) -> set[str]:
    """Все известные рантайму имена ``CLAY_*``.

    Объединение двух путей: (i) литеральные вхождения в исходниках и
    (ii) имена, генерируемые pydantic-settings из env_prefix + полей.
    """
    names: set[str] = set()
    src_dir = repo / "backend" / "src"
    for py in sorted(src_dir.rglob("*.py")):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        names.update(_ENV_TOKEN_RE.findall(text))
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        names |= _pydantic_generated_env_names(tree)
    return names


class TestDocHygiene:
    """Проверки документальной гигиены (D-53, D-55)."""

    def test_g1_unique_adr_numbers(self) -> None:
        """G1: один номер ADR = максимум один файл, кроме NNN-addendum-."""
        violations: list[str] = []
        seen: dict[str, str] = {}
        for path in sorted(_ADR_DIR.glob("*-*.md")):
            match = re.match(r"^(\d{3})-(addendum-)?", path.name)
            if not match:
                continue
            number = match.group(1)
            if match.group(2):
                continue
            if number in seen:
                violations.append(
                    f"{path.name}: номер {number} уже занят файлом {seen[number]}"
                )
            else:
                seen[number] = path.name
        assert not violations, "Коллизия номеров ADR:\n" + "\n".join(violations)

    def test_g2_adr_index_complete(self) -> None:
        """G2: каждый ADR-файл есть в индексе, каждая ссылка индекса существует."""
        readme = _ADR_DIR / "README.md"
        readme_text = readme.read_text(encoding="utf-8")
        violations: list[str] = []
        for path in sorted(_ADR_DIR.glob("*.md")):
            if path.name == "README.md":
                continue
            if path.name not in readme_text:
                violations.append(f"{path.name}: файл отсутствует в README.md")
        for match in re.finditer(r"\]\(([^)]+\.md)\)", readme_text):
            ref = match.group(1)
            if ref.startswith("http"):
                continue
            target = (readme.parent / ref).resolve()
            if not target.exists():
                violations.append(f"README.md: ссылка на несуществующий файл: {ref}")
        assert not violations, (
            "ADR-индекс неполон или указывает в никуда:\n" + "\n".join(violations)
        )

    def test_g3_reference_is_mkdocstrings_only(self) -> None:
        """G3: docs/reference/*.md — только заголовки, :::, опции и баннеры."""
        violations: list[str] = []
        for path in sorted(_REFERENCE_DIR.glob("*.md")):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    continue
                if stripped.startswith(":::"):
                    continue
                if stripped.startswith(">"):
                    continue
                if line[:1] in {" ", "\t"}:
                    continue
                violations.append(f"{path.relative_to(_REPO)}:{i}")
        assert not violations, "Прозa в generated-справке:\n" + "\n".join(violations)

    def test_g4_test_names_exist(self) -> None:
        """G4: каждый test_*-токен канона существует как def в backend/tests."""
        canon = _CANON.read_text(encoding="utf-8")
        tokens = set(re.findall(r"test_[a-z0-9_]+", canon))
        violations: list[str] = []
        for token in sorted(tokens):
            found = False
            for path in _TESTS_DIR.rglob("*.py"):
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if f"def {token}(" in text:
                    found = True
                    break
            if not found:
                violations.append(f"{token}: тест не найден в backend/tests")
        assert not violations, "Канон ссылается на несуществующие тесты:\n" + "\n".join(
            violations
        )

    def test_g5_env_vars_exist(self) -> None:
        """G5: каждый CLAY_*-токен канона известен рантайму."""
        canon = _CANON.read_text(encoding="utf-8")
        tokens = set(_ENV_TOKEN_RE.findall(canon))
        known = _runtime_env_names(_REPO)
        missing = sorted(token for token in tokens if token not in known)
        assert not missing, (
            "Канон ссылается на переменные, неизвестные рантайму "
            "(ни литералом, ни как <prefix>+<field>):\n"
            + "\n".join(f"{token} -> не найдено" for token in missing)
        )

    def test_g5_resolver_rejects_unknown_field(self) -> None:
        """Негативная проверка к G5: резолвер кусается на несуществующем поле."""
        known = _runtime_env_names(_REPO)
        assert any(name.startswith("CLAY_SCHEDULER_") for name in known), (
            "Префикс CLAY_SCHEDULER_ не найден среди известных имён — "
            "негативный тест не осмыслен"
        )
        assert "CLAY_SCHEDULER_NO_SUCH_FIELD_SECONDS" not in known

    def test_g6_migrations_exist(self) -> None:
        """G6: каждый номер миграции из канона существует в backend/alembic."""
        canon = _CANON.read_text(encoding="utf-8")
        numbers = set(re.findall(r"(?:migration|миграция)\s+(\d{4})", canon))
        violations: list[str] = []
        for number in sorted(numbers):
            matches = list(_MIGRATIONS_DIR.glob(f"{number}_*.py"))
            if not matches:
                violations.append(f"{number}: миграция {number}_*.py не найдена")
        assert not violations, (
            "Канон ссылается на несуществующие миграции:\n" + "\n".join(violations)
        )

    def test_g7_policy_paths_have_backend_prefix(self) -> None:
        """G7: путь к охранникам пишется как backend/tests/policy/."""
        violations: list[str] = []
        roots = [_REPO / "docs", _REPO / "backend" / "docs"]
        for root in roots:
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if "tests/policy/" in line and "backend/tests/policy/" not in line:
                        violations.append(f"{path.relative_to(_REPO)}:{i}")
        assert not violations, (
            "Путь tests/policy/ без префикса backend/ "
            "(правильная форма — backend/tests/policy/):\n" + "\n".join(violations)
        )
