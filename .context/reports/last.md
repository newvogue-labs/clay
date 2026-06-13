# Отчёт: сессия 2026-06-13 — docs-консолидация + FOOTGUN E + UI-F1a

## DOCS-RECON (read-only, 0 коммитов)
- ✅ R1–R7 инвентарь: 85 .md, 3 dirty .context/ (штатно), 0 untracked docs
- ✅ ADR-013/014/015 — свободны
- ✅ Obsidian/CachyOS: 300+ вхождений (build_specs/impl_plans/handoffs/historical docs)
- ✅ Phase R `docs/planning/`: 4 дубли (3 × 0-diff + 1 near-dupe с секцией 7.1), 3 planning-only

## DOCS-CONSOLIDATION (docs-only, 1 коммит `9e61966`)
- ✅ Blueprint §9–§10: иерархия ролей (4 яруса, roles-taxonomy.md как канон) + provider-pool + homo/hetero + RPD-бюджеты + degraded-mode
- ✅ 3 новых ADR: ADR-013 (provider-pool gateway-native), ADR-014 (config-snapshots prompt versioning), ADR-015 (degraded-mode, Accepted)
- ✅ Supersede deploy5: 3 файла (architecture + build_spec + impl_plan) → SUPERSEDED header
- ✅ Pointer-header 2 E5-файла + path-fix 44 вхождения Obsidian→`~/Projects/clay`
- ✅ Planning/ dedup: `git mv` skills-strategy/approved-stack → mission-control, `git rm` 5 planning/ файлов
- ✅ Backlog reorder: FOOTGUN A/D/F/G → closed, priority chain (provider-pool → retention → FOOTGUN E → роли → UI → хвосты)
- ✅ Index.md обновлён: ADR-013/014/015, ADR-006 reserved-gap, deploy5 → SUPERSEDED
- ✅ Проверка ссылок: 2 битых (`docs/README.md` + development/handoff — OOS)
- ✅ 22 файла, +312/-2046, 0 src/tests
- ✅ **463 baseline не двигался** (docs-only)
- ✅ API-слой консолидирован: ADR-013 v1 (gateway-native, 0 кода Clay), homo/hetero ратифицировано в blueprint §10.2
- ✅ Push `9e61966` → origin

## PROVIDER-POOL-RECON (read-only, 0 коммитов)
- ✅ R1: config.yaml — 4 model_name, все уникальны, pool НЕ используется
- ✅ R2: Router/fallbacks — НЕТ в config, Clay не зависит от litellm как Python-пакета
- ✅ R3: `_build_model_registry` — 6 моделей, model_id↔gateway model_name 1:1 строка. **VERDICT: pool = gateway-side, 0 кода Clay**
- ✅ R4: `INITIAL_ASSIGNMENTS` — 4 роли, model_id = alias 1:1
- ✅ R5: FOOTGUN E location — `runner.py:219`, `httpx.HTTPStatusError.response` теряется
- ✅ R6: psql — 10 tables в ops, provider/key/health table НЕТ, alembic head 0015
- ✅ R7: secrets — `/etc/clay/litellm/litellm.env` (600, uid 945), N-ключ-пул через `os.environ/KEY_N`

## UI-Ф1-RECON (read-only, 0 коммитов)
- ✅ Settings хардкод: `GPT-5.4`/`Gemini 3.1 Pro` в `settings-page.tsx:122-123`
- ✅ AI Console: полностью live, 3 вкладки, 0 mock
- ✅ `use-ai-control.ts` — уже есть (mount-fetch + SSE `ai-control.ready/refresh`)
- ✅ SSE `/ai-control/stream` — готов, heartbeat 15s
- ✅ GAP: 7 полей отсутствуют в `/ai-control/overview` (RPD, latency, error rate, tokens, runs summary, registry version, draft editor)

## FOOTGUN E fix (1 коммит `2084cee`)
- ✅ `runner.py`: новый `_format_gateway_error()` helper — 4xx/5xx → `"gateway HTTP <code>: <body[:500]>"`, transport error → `"[TypeName] <msg>"`
- ✅ Применён к LiteLLMModelClient + OllamaNativeClient except-блокам
- ✅ **3 новых hermetic теста:** 429 с body → "429", 400 пустое тело → "400", ConnectError → без AttributeError
- ✅ **466 passed** (+3, baseline 463), ruff 0, pyright 0

## UI-Ф1a (1 коммит `7106f9f`)
- ✅ `models.py`: 3 новых DTO — RoleRunSummary, RPDBudget, RegistryVersionInfo
- ✅ `service.py`: `_build_runs_summary()`, `_build_rpd_budgets()`, `_build_registry_version()`
- ✅ `repositories_ops.py`: `agent_runs_stats()` — 24h counting per role
- ✅ RPD limit map (static, per blueprint §10.4) + per-model rolling 24h consumption
- ✅ Registry fingerprint: sha256(sorted (model_id, transport, provider, status))[:12]
- ✅ `settings-page.tsx`: хардкод "GPT-5.4"/"Gemini 3.1 Pro" → live useAIControl
- ✅ NOT in slice: latency (Ф1b), token/cost (Ф1b), draft RPD editor (Фаза 2)
- ✅ **466 passed**, ruff 0, pyright 0

## Итог

| Track | Status |
|-------|--------|
| DOCS-CONSOLIDATION | ✅ CLOSED — `9e61966`, pushed |
| FOOTGUN E | ✅ CLOSED — `2084cee`, 2 unpushed |
| UI-Ф1a | ✅ CLOSED — `7106f9f`, 2 unpushed |
| PROVIDER-RECON | ✅ CLOSED — read-only, 0 коммитов |
| UI-Ф1-RECON | ✅ CLOSED — read-only, 0 коммитов |
| HEAD | `7106f9f` (2 unpushed) |
| pytest | 466 passed (baseline +3) |
