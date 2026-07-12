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
- **S5 (arch-maps):** ✅ 5 PR #35–#38 — Mermaid, C4, Module Map, Sequence, Data-flow, Boot-chain
- **H1–H3:** ✅ pre-commit check-yaml, deploy systemd units, untrack .context/
- **E-KNOW S1–S5:** ✅ vault bootstrap, taxonomy, ingest pipeline, peer review, first apply
- **E-KNOW S4 phase 2:** ✅ 4 advisory cards + sync idempotency + retrieval guaranteed slots
- **Knowledge Ablation Eval:** ✅ 3 scenarios × off/inject, M278=0, 4 cards used
- **E12.5:** ✅ CLOSED — all features done, branch-protection M275
- **S4-4a1:** ✅ MkDocs Material scaffold + curated nav (S4-1 PR #25, S4-2 PR #26, S4-3a/3b PR #26)
- **S4-4a2:** ✅ README rewrite + social cards + mkdocstrings + 4 reference pages (S4-4b PR #52, S4-3c PR #53, S6-1–S6-4a PR #54–#57)
- **S6-4b:** ✅ ai_control models docstrings — PR #58 → `a18cead`
- **S6-4:** ✅ knowledge models docstrings + reference — PR #59 → `8053b77`
- **S6-api:** ✅ API wiring reference — PR #60 → `33f8a72`
- **S4-4a2-a–e:** ✅ brand assets + README banner + MkDocs logo + vault brand — PR #61–#63 + 2 commits

## Завершено (текущая сессия — 2026-07-12)

### Defensive micro-package (S-DEF-1/2/3)
- **S-DEF-1:** README D1–D5 link fix — PR #64 → `cd5f226`
- **S-DEF-2:** ModelVersionSnapshot docstring fix — PR #65 → `e6612d4`
- **S-DEF-3:** docs.yml setup-python 3.13→3.14 — PR #66 → `5044378` (Pages GREEN run 29162411647)

### Live execution safety scaffolding (S-LIVE-1/2/3/5)
- **S-LIVE-2:** per-order notional hard-block guard — PR #67 → `e997f9d`
- **S-LIVE-1:** LiveExecutionClient real impl + guard wiring — PR #68 → `2ba2853`
- **S-LIVE-3:** real degraded-probe killswitch — PR #69 → `fd0ae93`
- **S-LIVE-5:** D9 comprehensive mocked-ccxt test matrix — PR #70 → `0f53ea8`

### T-BOOT (demo bring-up + .env.example fix)
- **T-BOOT D1:** .env.example fix (port 5433, execution-vars, scheduler off) — PR #71 → `65e16a2`
- **T-BOOT D2:** Local .env for bring-up — AI agent off, notional=50
- **T-BOOT Bring-up:** mise + compose + alembic + backend + frontend — all green
- **T-BOOT Assertions:** A1-A6 all pass (DB healthy, migrations head, backend 200, frontend 200, testnet mode, live coerced)

### S-TESTNET-1 (testnet-probe + notional-guard wiring)
- **S-TESTNET-1:** D1 bootstrap notional wiring + D2 testnet-probe endpoint + D3 router registration + D4 tests
  - PR #72 → `d5bb2a9`, 4 файла (+366 lines)
  - POST /workspace/trading/execution/testnet-probe (V1-V5 verdicts)
  - mode guard 409, notional guard 422, audit write, 5 tests
  - pyright 0, ruff 0, pytest 230 passed (API+execution suite)

### DOC ADR-032 + E14 (Architecture v2)
- **ADR-032:** Exchange Execution Adapter (Multi-Venue) — PR #73 → `3b44e12`
  - ADR-032 (177 lines) + README index fix (ADR-031 added + 033+) + E14 epic in backlog
  - mkdocs build --strict PASS, docs-only, 0 code changes

### S-ADAPT-1 (ExchangeAdapter port + domain layer / E14 slice 1)
- **S-ADAPT-1:** ExchangeAdapter Protocol + Decimal DTO + normalization — PR #74 → `314f809`
  - 12 files (+1080 lines), 0 diff in existing execution/
  - adapter/: enums, domain, rules, errors, normalization, port, __init__
  - 58 tests (domain, normalization, errors, port/FakeAdapter)
  - pyright 0, ruff 0, format 0, pytest 198 pass (58 new + 140 legacy)
  - ADR-032 errata: validate/quantize sync (not async) — doc fix pending

## In Progress

- **First controlled `--apply` vault→Notion** — Emma настраивает Notion integration + S2-3b даёт зелёный
- **S-LIVE-4** — открытие live mode через from_env (разрешение mode-coercion)
- **Frontend flaky** (`App.test.tsx:1477`: session lifecycle flaky) — симптом, не блокер

## Baseline

| Метрика | Значение |
|---------|----------|
| **HEAD (clay main)** | `3b44e12` (ADR-032 + E14) |
| **PR #74** | `feat/s-adapt-1-adapter-port` → main (awaiting merge) |
| **Alembic** | `0023_knowledge_external_id` (head) |
| **#knowledge** | 60 items |
| **PR open** | нет |
| **Reference pages** | 6 live (scheduler, signal_engine, execution, ai_control, knowledge, api) |
| **CI** | ✅ 33 PR merged total, все pass |
| **Brand assets** | ✅ clay + clay-knowledge (sha256 matched) |
| **pytest** | 930 passed + 58 adapter (988 total, soak excluded) |
| **Execution safety** | notional guard ✅, LiveExecutionClient ✅, degraded killswitch ✅, D9 matrix ✅, testnet-probe ✅ |
| **Demo stack** | Backend :8000 ✅, Frontend :5173 ✅, DB :5433 ✅, testnet mode ✅ |
| **ADR** | 032 accepted: Exchange Execution Adapter (Multi-Venue) |

## Next Step

Emma выбирает направление: S-LIVE-4 (open live mode), vault→Notion, новые reference-страницы, или другое.
