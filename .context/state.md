# Текущее состояние Clay

## Завершено (предыдущие сессии)

- **S-KELLY-2-R:** ✅ CLOSED — EV-gate block proof
- **S-RISKLIMITS-1/1b:** ✅ ADR-021 draft+recon+v2 — 5 session-level risk limits L1-L5
- **S-DOCSYNC-2:** ✅ MERGED (ADR doc-sync B + 015→018 + master-index, M214)
- **S-RUNTIME-VERIFY-1:** ✅ Ring 1 GO + FOOTGUN B verified + live gates (M215/M216)
- **S-RUFF-2:** ✅ ruff 58→0 + durability assertions (M217)
- **S-Ф1b-2:** ✅ ai_agent_runs indexes I1/I2 + retention 180d + ADR-023 (M218)
- **S-REPLAY-5:** ✅ MERGED (M226) — replay harness + faithful resolution (ADR-024)
- **S-REPLAY-6:** ✅ MERGED (M227) — real-data soak 5433 (62 sessions, 42W/19L), guard, ADR-024 Accepted
- **S-EGRESS-RECON-1:** ✅ CLOSED — testnet reachable из Paris (no 451), non-US egress map, ADR-008 integration point найден. Commit `e663019`.
- **S-EXEC-1 / ADR-025:** ✅ DRAFT — Execution Layer + Real-Money Gate (RV8) Proposed. testnet-first, 0 кода.
- **S-EXEC-2 / ADR-025 implementation:** ✅ MERGED — `TestnetExecutionClient` (ccxt) + integration. Commit `83fa532` (feat) + `43dce0c` (context/lock). Merge commit `fbd7c7f...`. Branch deleted.
- **S-EXEC-3a / Config unification:** ✅ MERGED — drop dead Pydantic `ExecutionConfig` from `config/models.py` (−14 lines), add `logger.warning` on live rejection in `execution/config.py`. Merge commit `bc64600` (no-ff). PR #1. Head: `bc64600`.
- **S-EXEC-4 / Testnet smoke:** ✅ MERGED — live smoke на `testnet.binance.vision`, adapter fixes (timeout, cancel_order, url). Скрипт + gated pytest. Merge commit `b23ef5d...`. Branch deleted.
- **S-EXEC-3b-1 / Schema + Repository:** ✅ MERGED — `ops.execution_overrides` table + `OverrideRepository`. PR #2. Head: `942177a`.
- **S-EXEC-3b-2 / OverrideService state machine:** ✅ MERGED — `OverrideService` с state machine, `rehydrate()`, 29 unit tests. PR #3. Head: `738fe1f`.
- **S-EXEC-3b-3 / API + wiring:** ✅ MERGED — override request/confirm/revoke endpoints, WorkspaceService integration, B1 wiring test, sync rehydrate, wire-fix. PR #4. Head: `223ccb9` (merge commit).
- **S-EXEC-3b-4 / LiveExecutionClient stub:** ✅ COMMITTED — `NotImplementedLiveClient` → `LiveExecutionClient` (D7 stub), factory wiring, B1-teardown `try/finally`. Commit `63e5871` (direct to main, 3b-4 = last slice).
- **S-EXEC-3c / Frontend TS-parity:** ✅ COMMITTED — 4 sub-slices (override-banner, confirm-modal, expire_in snapshot, localStorage mock fix). Commit `f51cb43`.
- **S-LINT-1c / src/ pyright 0:** ✅ CLOSED — 1c-a–1c-final. **338→0 errors.** HEAD `1fc3101`.
- **S-LINT-2 / 2a–2f** — 6 merges, 244→14 pyright. Head `f385dec`.

## Завершено (сессия 2026-07-01 — G1 close + DOC trilogy + S-CAPLIMITS-1)

- **G1 24h-soak:** ✅ CLOSED — 145 сэмплов / 144 healthy, t0+24h пройдено, финальный снапшот (`.soak/final-snapshot.md`), teardown штатный (сервисы остановлены), flip в release-gates.md (7/7 green → milestone).
- **DOC-1 (historical banners + ns notes + e3 numbering):** ✅ MERGED — commit `0754a3e`.
- **DOC-2 (ops-freshness):** ✅ MERGED — commit `b440a82`.
- **DOC-3 (index/cross-ref catch-up):** ✅ MERGED — commit `f0ccc18`.
- **S-CAPLIMITS-1 (exposure hard-block):** ✅ MERGED PR #6 — dual-tier off-by-default, `max_total_exposure_block_pct` (0.0=off). HEAD `d23585f`.
- **dev-DX:** `make backend-run` без `source .env`, 3 log-сообщения → DEBUG.
- **F6 refetch-loop:** 11 mount-эффектов исправлены (`[refresh]`→`[]`).

## Завершено (сессия 2026-07-02 — E2E аудит 8/12)

- **E12.5 E2E аудит — 8/12 экранов:** Workspace, Session Control, AI Control, Demo Validation, Validation Lab — specs написаны и прогнаны. Control Center — черновик spec.
- **P1 fix (F15):** `outcomeTone()` + `tone?`-проп на StatusBadge. Коммит `379dc3b`.
- **Readiness rollup verified:** бэкенд корректно ставит signal-alignment=fail при mismatched>0.

## Завершено (сессия 2026-07-03 — E2E аудит 12/12 + Batch A/B/C/D + интеграция)

- **E12.5 E2E аудит — 12/12:** дописаны и прогнаны Session Review (screen 9), Knowledge (screen 10), Reliability (screen 11), Settings (screen 12).
- **Batch A (StatusBadge tone) — F15/F17/F18/F21/F22:** создан `helpers/tone.ts` с `getOutcomeTone/matched→success, mismatched→danger, late→warning`, `getSeverityTone/critical→danger, warning→warning, info→muted`, `getPriorityTone/high→success, medium→warning, low→muted`. Коммит `ae70369`. БАГФИКС: `fix/E12.5-batchA-statusbadge-tone` включал лишнее (stash, не чистая feature) — пересоздан как чистый коммит с `helpers/tone.ts` + 4 panel wirings.
- **Batch B (dead-end flows) — F12/F13/F16:** close-review UI кнопка + `session.review_closed` в SSE + discard endpoint + upsert `review_activation`. Коммит `f4ae839`.
- **Batch C (F23 settings wire):** `types/settings.ts`, `api/settings-client.ts`, `use-settings.ts`. Risk-лимиты из `/configs`. Apply/restore config-review UI. Коммит `a17a362`.
- **Batch D (F9 content=null fix):** normalize content=null in adapter.py от LiteLLM. Коммит `a7f5935`.
- 🚀 **Интеграция A+B+C+D:** ветка `integration/E12.5-fixes`, SHA `1223a15`. Все 4 батча слиты. Тур-гейт 6/6 → 7/7 (добавлен validation-lab). **MERGE в main:** `1223a15`. Fast-forward, без конфликтов.
- **E2E туры:** 7 штук (demo-validation-c-recheck, knowledge, reliability, session-control, session-review, settings, validation-lab) — все зелёные. Badges цветные (не muted) — критический критерий закрыт.

## Baseline

| Метрика | Значение |
|---------|----------|
| **HEAD (main)** | `c4d5a34` — Batch A/B/C/D/E слиты |
| **Batch F** | `f05359c` (ветка `fix/E12.5-batchF-session-review-filters-scope`), не слит |
| **Batch E (sweep)** | `c4d5a34` |
| **Batch A (tone)** | `ae70369` |
| **Batch B (dead-end)** | `f4ae839` |
| **Batch C (settings)** | `a17a362` |
| **Batch D (content-null)** | `a7f5935` |
| **Ruff** | **0** |
| **Pyright (src/)** | **0 errors** |
| **tsc (frontend)** | **0** |
| **Vitest** | **17 passed** |
| **Playwright E2E** | **7/7 passed** |
| **Pytest config** | **62 passed** |
| **Alembic** | 0021 (execution_overrides, 5433) |
| **ADR** | 001–029 |

## Critical Context

- **Рабочая БД:** `127.0.0.1:5433` (podman clay_timescaledb, TS 2.27.1)
- **G1:** closed. Release-gates: 7/7 green.
- **S-CAPLIMITS-1:** PR #6 squash-merged, `max_total_exposure_block_pct = 0.0` (off-by-default).
- **Playwright E2E:** headless chromium, `:4173` (production build). Артефакты в `/tmp/workspace-tour/`.
- **StatusBadge tone-prop:** `getSeverityTone`/`getOutcomeTone`/`getPriorityTone` в `helpers/tone.ts` (shared). Все 4 панели (session-review, knowledge, reliability) получают tone prop — badges цветные.
- **Batch D (F9):** `content=null` нормализуется в `adapter.py` строкой 21 → всегда non-null.
- **CI:** последний ран #28506529830 success.

## In Progress

- **Batch F (F19+F20):** Interactive filters (strategy/model/confidence button grids + time Unimplemented) + session-level scope fix (sessionSummary preserves review_status/last_reviewed_at/feedback_count across filter changes). Ветка `fix/E12.5-batchF-session-review-filters-scope` на `f05359c`, запушена. Ждёт loadFile-верификации от Emma.

## Next Step

**Ждёт решения Emma:**
1. **Batch F → main:** После loadFile-верификации — FF-merge в `main`. SHA `f05359c`.
2. **Ring 1 GO** — после sign-off Emma.
3. **G2** — следующий milestone.
4. **Real-money GO** — продуктовый sign-off Emma (Q5).
