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


_ADR_STATUS_WORDS = {
    "Proposed",
    "Accepted",
    "Rejected",
    "Superseded",
    "Deprecated",
}

_ADR_STATUS_ANY_RE = re.compile(
    r"\b(" + "|".join(sorted(_ADR_STATUS_WORDS)) + r")\b", re.IGNORECASE
)
_ADR_ROW_RE = re.compile(
    r"^\|\s*(\S+?)\s*\|\s*(.+?)\s*\|\s*(\S+?)\s*\|\s*(\S+?)\s*\|\s*(.+?)\s*\|$"
)


def _status_word_in_line(line: str) -> str | None:
    match = _ADR_STATUS_ANY_RE.search(line)
    if match:
        return match.group(1).capitalize()
    return None


def _extract_adr_status(path: Path) -> str | None:
    """Извлечь токен статуса ADR из шапки файла.

    Формат строки статуса свободный: ``- **Status:** Accepted (... )``,
    ``**Status:** …``, ``> Status: …``, ``Статус: …`` или секция
    ``## Status`` со значением в следующей строке. Токен — первое слово
    из словаря; всё после него (скобки, тире, пояснение) игнорируется.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    head = lines[:40]
    for i, line in enumerate(head):
        if line.strip().lstrip("#").strip() in {"Status", "Статус"}:
            for nxt in head[i + 1 : i + 5]:
                word = _status_word_in_line(nxt)
                if word:
                    return word
    for line in head:
        if re.search(r"(?:Status|Статус)\s*:", line):
            word = _status_word_in_line(line)
            if word:
                return word
    return None


def _parse_adr_index(readme: Path) -> list[dict[str, str]]:
    """Распарсить таблицу ADR в README.

    Пропускаются явно и осознанно: строки без трёхзначного номера ADR
    (аддендумы, резервы, «040+») и строки со статусом «—» (reserved-gap,
    резервы номеров) — у них нет ни номера ADR, ни статуса.
    """
    rows: list[dict[str, str]] = []
    for line in readme.read_text(encoding="utf-8").splitlines():
        match = _ADR_ROW_RE.match(line)
        if not match:
            continue
        number, title, status, location, link = match.groups()
        if not re.fullmatch(r"\d{3}", number):
            continue
        if status == "—":
            continue
        rows.append(
            {
                "number": number,
                "title": title,
                "status": status,
                "location": location,
                "link": link,
            }
        )
    return rows


def _adr_file_for_row(row: dict[str, str], repo: Path) -> Path:
    base = re.search(r"([\w-]+\.md)\)", row["link"])
    assert base, f"не удалось извлечь имя файла из ссылки: {row['link']}"
    if row["location"] == "mc-archive":
        return repo / "docs" / "mission-control" / "adrs" / base.group(1)
    return repo / "docs" / "adr" / base.group(1)


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
        """G3: в теле docs/reference/*.md (от первой :::) проза запрещена.

        Файл делится границей — первая строка, начинающаяся с ``:::``.
        Зона шапки (всё до неё) — место вводного баннера, разрешено что
        угодно. Зона тела (от первой ``:::`` и до конца): только пустые
        строки, заголовки ``#``, строки ``:::`` и строки с ведущим
        пробелом/табом (опции директив). Любая иная непустая строка —
        включая начинающиеся с ``>`` и с ``-`` — нарушение. Если в файле
        нет ни одной директивы ``:::``, весь файл считается зоной тела.
        """
        violations: list[str] = []
        for path in sorted(_REFERENCE_DIR.glob("*.md")):
            lines = path.read_text(encoding="utf-8").splitlines()
            boundary = next(
                (i for i, line in enumerate(lines) if line.strip().startswith(":::")),
                0,
            )
            for i, line in enumerate(lines, 1):
                if i <= boundary:
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    continue
                if stripped.startswith(":::"):
                    continue
                if line[:1] in {" ", "\t"}:
                    continue
                violations.append(f"{path.relative_to(_REPO)}:{i}")
        assert not violations, (
            "Проза в теле generated-справки — перенесите факт в "
            "backend/docs/execution.md:\n" + "\n".join(violations)
        )

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

    def test_g8_adr_statuses_consistent(self) -> None:
        """G8: статусы ADR в индексе совпадают с шапками файлов.

        (а) статус в таблице == токену из файла (регистронезависимо), значение
        обязано быть из словаря; (б) если ADR Accepted и в его тексте «заменён
        на … (ADR-NNN)», целевой ADR-NNN не может быть Proposed; (в) строки
        таблицы без числового номера и со статусом «—» пропускаются явно в
        ``_parse_adr_index``, не побочным эффектом.
        """
        violations: list[str] = []
        rows = _parse_adr_index(_ADR_DIR / "README.md")
        if not rows:
            violations.append("README.md: в таблице ADR не найдено ни одной строки")
        by_number: dict[str, dict[str, str]] = {}
        for row in rows:
            number = row["number"]
            by_number[number] = row
            path = _adr_file_for_row(row, _REPO)
            if not path.exists():
                violations.append(
                    f"{number}: файл не существует {path.relative_to(_REPO)}"
                )
                continue
            file_status = _extract_adr_status(path)
            if file_status is None:
                violations.append(
                    f"{number}: в файле {path.relative_to(_REPO)} не найдена "
                    "строка статуса"
                )
                continue
            if row["status"].lower() != file_status.lower():
                violations.append(
                    f"{number}: индекс {row['status']!r} != файл {file_status!r} "
                    f"({path.relative_to(_REPO)})"
                )
        for row in rows:
            if row["status"].lower() != "accepted":
                continue
            path = _adr_file_for_row(row, _REPO)
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(
                r"(?:superseded\s+by|replaced\s+by|заменён(?:\s+на)?"
                r"|заменены(?:\s+на)?|замена\s+на).*?ADR-(\d{3})",
                text,
                re.IGNORECASE,
            ):
                target = by_number.get(match.group(1))
                if target is not None and target["status"].lower() == "proposed":
                    violations.append(
                        f"{row['number']} (Accepted) объявляет замену на "
                        f"ADR-{target['number']}, но та всё ещё Proposed"
                    )
        assert not violations, "Несогласованность статусов ADR:\n" + "\n".join(
            violations
        )

    def test_g8_status_dictionary_defined_in_readme(self) -> None:
        """G8: словарь статусов в README (## Правило) == хардкод в тесте.

        Ищется строка, начинающаяся с ``**Статусы ADR (канонический словарь):``,
        и словарь собирается ТОЛЬКО из неё — остальная преамбула на результат
        не влияет (иначе случайный CapitalCase-токен в бэктиках ложно ронял бы
        тест).
        """
        readme = (_ADR_DIR / "README.md").read_text(encoding="utf-8")
        rule = readme.split("## Полная таблица", 1)[0]
        dictionary_line = next(
            (
                line
                for line in rule.splitlines()
                if line.strip().startswith("**Статусы ADR (канонический словарь):")
            ),
            "",
        )
        assert dictionary_line, "В README (## Правило) нет строки словаря статусов"
        listed = set(re.findall(r"`([A-Za-z]+)`", dictionary_line))
        assert listed == _ADR_STATUS_WORDS, (
            "Словарь статусов в README (## Правило) расходится с хардкодом в "
            f"тесте: в README {sorted(listed)} vs код {sorted(_ADR_STATUS_WORDS)}"
        )

    def test_g9_doc_relative_paths_exist(self) -> None:
        """G9: все относительные .md-пути в документации существуют.

        Два раздельных вида ссылок с раздельным резолвом:
        ``kind="md"`` — markdown-ссылки ``[...](….md)``, резолвятся ТОЛЬКО
        от ``path.parent``; ``kind="plain"`` — пути вида
        ``docs/….md``/``backend/….md`` в тексте, резолвятся ТОЛЬКО от корня
        репо. Пустой вход (ноль ссылок) — падение, «нет данных» не читается
        как «нет нарушений».
        """
        md_link_re = re.compile(r"\]\(([^)]+?\.md)(?:#[^)]*)?\)")
        plain_re = re.compile(r"(?<![\w/-])((?:docs|backend)/[\w./-]+\.md)(?![\w])")
        refs: list[tuple[Path, int, str, str]] = []
        roots = [_REPO / "docs", _REPO / "backend" / "docs"]
        for root in roots:
            for path in sorted(root.rglob("*.md")):
                for i, line in enumerate(
                    path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                ):
                    for match in md_link_re.finditer(line):
                        ref = match.group(1)
                        if ref.startswith(("http", "/", "#")):
                            continue
                        refs.append((path, i, ref, "md"))
                    for match in plain_re.finditer(line):
                        refs.append((path, i, match.group(1), "plain"))
        refs = sorted(set(refs))
        violations: list[str] = []
        if not refs:
            violations.append("не найдено ни одной .md-ссылки — пустой вход")
        for path, i, ref, kind in refs:
            target = (
                (path.parent / ref).resolve()
                if kind == "md"
                else (_REPO / ref).resolve()
            )
            if not target.exists():
                violations.append(
                    f"{path.relative_to(_REPO)}:{i} → [{kind}] {ref} "
                    f"(ожидался {target.relative_to(_REPO)})"
                )
        assert not violations, (
            "Битые относительные .md-пути в документации:\n" + "\n".join(violations)
        )
