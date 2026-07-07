---
date: 2026-06-02
type: fix
applies-to: [clay, opencode, m3-free, pyright, venv, lsp]
status: ratified (env-fix applied, 0 missing-imports)
tags: [type-checker, pyright, venv, lsp, env-config, dev-loop]
---

# obs-2026-06-02-003: Pyright LSP не подхватывает venv → CLI-pyright = source of truth

## Проблема

OpenCode M3 с Pyright LSP показывал **каскад** ошибок типа "could not be resolved" / "for class object" / "No parameter named" на **зелёном** коде (215 passed pytest, ground truth). Причина: LSP смотрел в системный Python (или пустое окружение), а не в `.venv` проекта. После **env-фикса** (без правок кода) — 0 `reportMissingImports` в CLI-pyright. Editor-LSP подтянется после restart server.

## Симптомы

| Симптом | Причина |
| --- | --- |
| `Import "pytest"/"fastapi"/"apscheduler"/"sqlalchemy" could not be resolved` | deps есть в venv, Pyright смотрит мимо |
| `Cannot access attribute "X" for class "object"` | типы сервисов из нерезолвнутых модулей → `Unknown` → `object` |
| `No parameter named "Y"` | **stale index** — параметры на диске есть, Pyright читает устаревший кеш / неверный env |

## Фикс (env-only, ~5 минут, без правок кода)

**1. Путь к venv-интерпретатору (ground truth):**

```bash
cd /home/emma/Projects/clay/backend
uv run python -c "import sys; print(sys.executable)"
# → /home/emma/Projects/clay/backend/.venv/bin/python3
```

**2. `backend/pyrightconfig.json`:**

```json
{
  "venvPath": ".",
  "venv": ".venv",
  "pythonVersion": "3.14",
  "typeCheckingMode": "basic",
  "include": ["src", "tests"],
  "exclude": ["**/__pycache__", "**/.pytest_cache", "**/node_modules", ".venv", "alembic"]
}
```

**Важно:** `venvPath` (директория, где лежит venv) и `venv` (имя venv) — **оба** обязательны. Без `venvPath` Pyright иногда не находит venv.

**3. Очистить Pyright-кеш:**

```bash
rm -rf ~/.cache/pyright
# + project-local: rm -rf backend/.pyright_cache
```

**4. CLI-pyright = source of truth (Architect guidance):**

```bash
cd /home/emma/Projects/clay/backend
uvx --from pyright pyright  # не editor popup
```

**НЕ** editor LSP popup (он использует свой кеш). **CLI-pyright читает файлы с диска и venv напрямую**.

**5. Editor-LSP reload** (в редакторе): command palette → "Pyright: Restart Server" / reload window.

## Verification (после фикса)

```bash
# 1. CLI-pyright (authoritative):
uvx --from pyright pyright --outputjson | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
groups = {}
for d in data.get('generalDiagnostics', []):
    groups[d.get('rule', '?')] = groups.get(d.get('rule', '?'), 0) + 1
print(data.get('summary'))
for r, c in sorted(groups.items(), key=lambda x: -x[1]):
    print(f'  {c:4d}  {r}')
"
# Expected: 0 reportMissingImports, остальное — реальные type issues
```

Pre-fix в Clay: 0 → 184 (после env-fix). Все 184 — `reportIndexIssue` / `reportAttributeAccessIssue` / `reportArgumentType` / `reportOptionalMemberAccess` / `reportGeneralTypeIssues` / `reportReturnType` / `reportInvalidTypeForm`. **Ни одного** `reportMissingImports`. 7 в B4-файлах (5 pre-existing test-helper + 2 B4 test-fake type-hygiene), 177 pre-existing в production коде. Ratified: "не трогаем сейчас" (YAGNI-гигиена, не баг).

## Why

Architect был прав с первого захода — проблема не в `Optional`-DI / `TypedDict ClayServices`, а в **окружении типчекера**. Код зелёный и корректный (`pytest -q` → 215 passed — runtime ground truth). 90% повторяющегося LSP-шума уйдёт после одного env-фикса.

## How to apply

**Когда в новой сессии / новом проекте снова видишь каскад "could not be resolved" / "for class object" при зелёном pytest:**

1. **Сначала** проверь pytest — если зелёный, проблема в LSP, не в коде
2. **Запусти** `uvx --from pyright pyright` — source of truth
3. **Если** `reportMissingImports > 0` — фикси окружение (см. выше)
4. **Если** `reportMissingImports = 0` — это **реальные** type issues в коде, чини по обстоятельствам
5. **Параллельно** — рестартни editor LSP (reload window / "Pyright: Restart Server")

**Чего НЕ делать:**

- ❌ Не добавлять `Optional` / `TypedDict` / type: ignore "чтобы заглушить" — лечи симптомы, не причину
- ❌ Не доверять editor LSP popup как ground truth — используй CLI-pyright
- ❌ Не пропускать `venvPath` в config — без него venv может не найтись

## Carry-forward (для других проектов)

Этот фикс — **generic dev-loop pattern** для любого Python-проекта с `uv` venv:

1. **Всегда** коммитить `pyrightconfig.json` (или `[tool.pyright]` в `pyproject.toml`) в корень Python-пакета
2. **`venvPath: "."`** + **`venv: ".venv"`** — минимальный набор для `uv` проектов
3. **`pythonVersion`** — должна совпадать с `[project.requires-python]` в `pyproject.toml` (или `.python-version` для mise)
4. **`typeCheckingMode: "basic"`** — не `strict` (strict ловит слишком много для AI-агент цикла)
5. **CLI-pyright в CI** — отлавливает "забыл обновить кеш" / "wrong env" / "pre-existing type debt" в одном месте
