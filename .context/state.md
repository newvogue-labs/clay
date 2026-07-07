# Текущее состояние Clay

## Завершено (предыдущие сессии)

- **S-KELLY-2-R:** ✅ CLOSED
- **S-RISKLIMITS-1/1b:** ✅ ADR-021 draft+recon+v2
- **S-DOCSYNC-2:** ✅ MERGED (ADR doc-sync B + 015→018 + master-index, M214)
- **S-RUNTIME-VERIFY-1:** ✅ Ring 1 GO + FOOTGUN B verified + live gates (M215/M216)
- **S-RUFF-2:** ✅ ruff 58→0 + durability assertions (M217)
- **S-Ф1b-2:** ✅ ai_agent_runs indexes I1/I2 + retention 180d + ADR-023 (M218)
- **S-REPLAY-5:** ✅ MERGED (M226) — replay harness + faithful resolution (ADR-024)
- **S-REPLAY-6:** ✅ MERGED (M227) — real-data soak 5433 (62 sessions, 42W/19L), guard, ADR-024 Accepted
- **S-EGRESS-RECON-1:** ✅ CLOSED
- **S-EXEC-1–S-EXEC-4 / ADR-025:** ✅ TestnetExecutionClient (ccxt), Config unification, Testnet smoke, Execution override schema/service/API/frontend/live stub
- **S-LINT-1c / S-LINT-2:** ✅ pyright src/ 338→0 errors
- **G1 24h-soak:** ✅ CLOSED — 145 семплов / 144 healthy
- **DOC-1/2/3:** ✅ MERGED — historical banners, ops-freshness, index/cross-ref
- **S-CAPLIMITS-1:** ✅ PR #6 — exposure hard-block off-by-default
- **dev-DX:** `make backend-run` --env-file, 3 logs DEBUG
- **F6 refetch-loop:** 11 mount-эффектов исправлены

## Завершено (текущая сессия — 2026-07-06)

### M278 detector (Layer A output-scan) — PR #21 → main ✅
- **CommandDetector** в `commands.py` — verb sets EN+RU (44 глагола), numeric direction/leverage regex, excluded compounds (shortlist/long-term/orderbook/buying/selling/setup/stop-loss)
- **0 FN** на 52 реальных командах, **6 FP** задокументированы
- **Тест-корпус** закоммичен (REAL_COMMANDS + ADVISORY_PHRASES)
- **Integration** — `m278_scan.py` (standalone), +M278 report в `knowledge_ablation_llm.py`
- **Makefile** — `backend-eval-m278`, `backend-eval-ablation`
- **114/114 pass**, ruff 0, pyright 0
- **PR #21** merged → main @ `444482f`

### Full ablation eval (minimax-m3) — 3 сценария × off/inject ✅
- **M278: 0 violations** на всём корпусе (6/6 outputs)
- **kn-91** цитирован в quiet/inject — pre-trade checklist полезен
- **kn-92** execution — НЕ появляется нигде (EXCLUDED_TAGS работает)
- **interp cards:** kn-84 (3/3), kn-95 (3/3), kn-96 (3/3), kn-85 (1/3), kn-83 (1/3), kn-86 (1/3)
- **Inject лучше off** по всем сценариям: структурированные таблицы, framework, provenance
- **Замечание:** strong/mixed inject выводы обрезаны (max_tokens=512 мало)

### Находка B — split execution-checklist + exclude barrier + backfill external_id ✅
- **C1:** split `market/execution-checklist` (kn-34) → `pre-trade-checklist` (kn-91, process) + `execution-checklist` (kn-92, execution-only, `tags=[execution]`)
- **C2:** `_EXCLUDED_TAGS = {"execution"}` filter in `_retrieve_advisory_cards()` — execution-tagged cards physically cannot reach chief-agent prompt
- **C3:** sync vault → knowledge: 57 items, 0 duplicates
- **C4:** ADR-030 updated — split + exclude barrier documented
- **C5:** unit test + 133/133 pass, ruff 0, pyright 0
- **C6:** backfill `external_id` on 48 vault-sourced cards (were NULL → ghost on any edit). Verified: edit `risk/atr-stop` → UPDATE in place at id=52, no ghost
- **PR #19:** `feature/nakhodka-b-split-checklist` на main

### Карты 3/4 — signal-confluence + regime-market-health ✅
- kn-95 `signals/regime-market-health` (observation, high)
- kn-96 `signals/signal-confluence` (observation, medium)
- Advisory voice (M278-safe), funding two-stage (soft ±0.1%/8h, hard ±0.3%/8h), VPIN contested
- Sync: count=59, idempotent

### Wiring — expand interp query + 3-tier slot alloc ✅
- `_STANDING_INTERP_QUERY` expanded with regime/confluence/funding/liquidity/microstructure/correlation/volatility
- kn-95 score: 0.3 → 2.3
- 3-tier slot alloc: guaranteed (6 interp) → reserved (dynamic, up to 2) → fillable (risk/checklist)
- `_MAX_CARDS=15` as upper bound, char-cap=2000 is binding
- 30/30 tests, ruff 0, pyright 0
- Multi-snapshot: all 6 interp in every snapshot
- **PR #20:** `feature/wiring-interp-retrieval` на main

### E-KNOW S4 — peer review всего корпуса clay-knowledge ✅
- 4 домена, 49 карточек: signals (3) + risk (13) + market (18) + strategy (15)
- Все `draft → peer_reviewed`
- Найдено и исправлено 2 ошибки: Chandelier Exit (2 файла), Kelly comparison (1 файл)

### E-KNOW S5 — первый --apply vault→#knowledge ✅
- 49/49 items synced, 0 ошибок
- Найден backend bug (VARCHAR overflow) → миграция `df9cf24f3af4`
- Манифест закоммичен, vault @ `f10e217`

### E-KNOW S4 phase 2 — 4 advisory cards + sync idempotency + retrieval guaranteed slots ✅
- 4 advisory карты (83-86) в vault: signals/noise-vs-signal, rank-confidence-kelly, data-freshness-discount, posture-flag-triggers
- Idempotent vault sync: `external_id` + UNIQUE CONSTRAINT + upsert API — PR #17
- 2 бага post-PR#17: migration constraint vs index fix, duplicated external_id in .values() — пофикшено
- Guaranteed retrieval: `_STANDING_INTERP_QUERY` + `guaranteed_ids` + `_MAX_CARDS=14` — PR #18
- Multi-snapshot verification: 3/3 snapshots — все 4 карты present

### Knowledge Ablation Eval (minimax-m3) ✅
- 3 сценария (quiet, volatile, mixed) × off vs inject = 6 прогонов LLM
- **M278: 0 violations** в inject — advisory-only на 100%
- **Все 4 карты (83-86) использованы** LLM в inject-режиме
- **Карта 84 (rank-confidence-kelly)** — самая impactful (все 3 сценария)
- **Карта 86 (posture-flag-triggers)** — situational (только volatile сценарий)
- INJECT-ответы структурированнее, конкретнее, decisive чем OFF

### Batch F (F19+F20) verification + landing
- F24 (Vitest scope src/) — PR #8 → `d2364ce`
- Batch F rebase + squash-merge PR #7 → `59119c8`
- Landing sweep: все Batch A–F подтверждены

### Batch G (P2 cosmetic) — PR #9 → `5d89729`
- F7: alpha label flicker — `Loading…` fallback
- F8: nav click swallow — `AnimatePresence mode="wait"` → default
- F14: ai-control `Review` → `Stage {model}…` + tooltip
- F29: `git rm` 3 orphan knowledge panels

### Batch H (knowledge-polish) — PR #10 → `14be6e9`
- F27: `DELETE /knowledge/items/{id}` — бэк+фронт+тесты
- F28: `isLoading: true` в `refresh()` — консистентность

### Branch-protection (M275) — PR #11
- `enforce_admins=true`, strict `backend`/`frontend`, required PR, linear history, no force-push/deletions
- PR #11 — первый под новым гейтом
- M271 dev-DX recon: `de10b26` предок main → **уже на main**

### Dead-code cleanup — PR #11 → `a02bc78`
- `workspace-state-banner.tsx` — 0 импортов → `git rm`

### E12.5 CLOSED
- F7/F8/F14/F15/F17/F18/F21/F22/F23/F27/F29 → done
- F28 → non-issue-cosmetic
- F2/F26 → wontfix
- M275 (red-main дыра) → branch-protection закрыта структурно

### E-KNOW S1 — vault bootstrap ✅
- `~/Projects/clay-knowledge/` — OKF-скелет, git init @ `9127736`
- D1–D7: AGENTS.md, index.md, log.md, 5 donor, 5 concept, tree references/concepts/mocs

### E-KNOW S1-доп — таксономия ✅
- master → main, 8 MOC-заглушек (market/strategy/risk/signals/agents/ops/method/donors)
- Доменная таксономия + frontmatter-конвенции в AGENTS.md
- Backfill id/domain/runtime_eligible на 10 файлах
- vault @ `4d22bc7`

### E-KNOW S1-доп-2 — kb_category ✅
- `kb_category` в конвенции (note|strategy_rule|checklist|observation)
- vault @ `0bf4cb1`

### E-KNOW S3 — ingest pipeline vault→KB 🔶 PR #12 open
- `backend/src/clay/knowledge/sync.py` — build_plan, manifest, dry-run/apply
- CLI: `python -m clay.knowledge.sync` + `make backend-sync`
- 8 тестов, ruff/pyright 0, full suite 762/762 pass
- PR #12: `feature/E-KNOW-S3-vault-sync` @ `140240c`

## Baseline

| Метрика | Значение |
|---------|----------|
| **HEAD (main)** | `444482f` (PR #21: M278 detector) |
| **HEAD (vault)** | `f397867` (kn-95 + kn-96 + split) |
| **Alembic** | `df9cf24f3af4` (0022, head) |
| **Backend migration** | `source_type VARCHAR(32)→VARCHAR(64)` applied |
| **#knowledge items** | 59 (51 vault + 4 advisory 83-86 + 2 process 91-92 + 2 new 95-96) |
| **PR open** | нет |
| **Branch-protection** | `enforce_admins=true`, strict checks `backend`/`frontend`, required PR, linear history |
| **Ruff / Pyright / tsc** | 0 |
| **Vitest / E2E** | 17/17 / 7/7 (frontend: pre-existing flaky test, не блокирует) |
| **Pytest** | 114 pass (scheduler suite), full suite pass |
| **ADR** | 001–030 |

## In Progress

- **M278 детектор (Layer A output-scan) — CLOSED** ✅ (PR #21, main @ `444482f`)
- **Ablation eval (minimax-m3) — CLOSED** ✅ (0 M278 violations, inject ценнее off)
- **Valve NOT opened** — `ai_agent_knowledge_mode` = `"off"` in prod
- **Очередь:** карта 7 (source-credibility-filter) → Q5-GO → открыть valve
- **Layer B (_sanitize precision-pass)** — отложен, не в этом слайсе

## Next Step

Выбор Emma:
1. **Карта 7 (source-credibility-filter)** — после M278
2. **Q5-GO** — execution layer, real-money gate
3. **Открыть valve** — переключить `ai_agent_knowledge_mode` → `"inject"`
4. **Layer B (sanitize precision-pass)** — входной чистильщик card-текста
