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

## Завершено (текущая сессия)

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
| **HEAD (main)** | `a02bc78` |
| **HEAD (vault)** | `0bf4cb1` |
| **PR open** | #12 — E-KNOW S3 vault→KB sync |
| **Branch-protection** | `enforce_admins=true`, strict checks `backend`/`frontend`, required PR, linear history |
| **Ruff / Pyright / tsc** | 0 |
| **Vitest / E2E** | 17/17 / 7/7 |
| **Pytest CI** | success |
| **Alembic** | 0021 |
| **ADR** | 001–029 |

## In Progress

- **E-KNOW S3** — PR #12 open, ждёт код-верификацию + merge
- **Q5-GO** — параллельно

## Next Step

1. **S3 код-верификация + merge** — Emma проверяет PR #12
2. **Наполнение market/strategy/risk доменов** — первый настоящий Wolf-контент в vault
3. **Q5-GO** — execution layer, real-money gate (параллельно)
4. **Sampler `--noproxy`** — deferred до следующего soak-прогона
