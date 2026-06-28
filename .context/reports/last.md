# Отчёт: сессия 2026-06-28 — S-LINT-1c-final (tail + CI ratchet)

## Что сделано

### 1c-d-tail — conformance tests (+2)
- `backend/tests/execution/test_execution_config.py`: +2 теста `isinstance(client, ExecutionClient)` для dry_run + testnet clients
- **Коммит:** `000a123` — CI success ✅

### 1c-final — CI-pyright ratchet
- **`.github/workflows/ci.yml`:** pyright разделён на blocking src/ (`uv run pyright src`, blocking) + informational full (`uv run pyright`, `continue-on-error: true`)
- **`backend/pyproject.toml`:** удалён мёртвый `[tool.pyright]` (полностью перебивался `pyrightconfig.json` с `include: ["src","tests"]`)
- **`Makefile`:** добавлен `backend-typecheck-src` (локальный паритет CI-гейту)
- **Коммит:** `1fc3101` — CI success ✅ (run 28327740226)

### 🔍 Обнаруженная ловушка
`pyrightconfig.json` **полностью перебивает** `[tool.pyright]` в `pyproject.toml` — pyright не мёржит их. Мёртвый блок удалён, оставлена хлебная крошка.

## Регресс-база

- **Full suite:** **738 passed / 2 deselected / ruff 0**
- **Pyright (src/, blocking):** **0 errors**
- **Pyright (full, incl tests/):** **244 errors (informational, S-LINT-2)**

## Итог

**HEAD `1fc3101`.** S-LINT-1c официально CLOSED ✅

## Next

Выбор Emma: S-LINT-2 (pyright full → 244→0 → убрать informational CI-шаг) или донор-слайс.
