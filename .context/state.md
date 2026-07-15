# Текущее состояние Clay

## Завершено (предыдущие сессии)

...

## Завершено (текущая сессия — 2026-07-14)

### S-EXEC-SAFE-2b-1b: gate wiring + route consolidation (testnet only)

- **PR #87:** MERGED `a8b1ee3fbf3f48ac00302f3e272be8341e482ce7` (squash)
  - 8 файлов, +493/−52
  - ExecutionProofGate wrapper + errors + route consolidation
  - bootstrap: wrap in ExecutionProofGate (armed/testnet only)
  - 437 tests: all green

### S-EXEC-SAFE-2b-1a: proof-gate durable persistence (dormant)

- **PR #86:** MERGED `bbbc729c06b559bbe3ccd04df229006974ab7ce5` (squash)
  - 4 файла, +335/−0
  - ExecutionProofDecision ORM + from_record + ProofDecisionRepository
  - alembic 0024: down_revision=0023, reversible
  - 8 tests: from_record, round-trip, serde, migration smoke

### S-EXEC-SAFE-2b-0: fail-closed for uncomputable notional (dormant)

- **PR #85:** MERGED `aa7ff45881e73f45f710edae1eee5be6a47626b2` (squash)
  - 4 файла, +81/−1
  - NOTIONAL_UNCOMPUTABLE appended, rule 10 split, 4 unit + 1 Hypothesis
  - Dormant: 0 refs outside proof/

### S-EXEC-SAFE-2a: proof-gate pure checker + reason-codes + decision-record (dormant)

- **PR #84:** MERGED `c953eca21ba05853d188f0155972ce52e17431a7` (squash)
  - 12 файла, +996/−6
  - `execution/proof/`: reason_codes, snapshot, decision, checker, __init__
  - F-4: `ExecutionConfig.max_order_notional_usdt` float→Decimal
  - 23 unit tests + 2 Hypothesis anti-drift tests
  - icontract==2.7.3, hypothesis==6.156.6
  - All gates G1–G8 confirmed

### ADR-033 Execution Proof-Gate — doc-only draft

- **PR #83:** MERGED `fa127da8d5aed9e1a38942652f8ea2a0462aafd7` (squash)
  - 2 файла, +207/−1
  - `docs/adr/033-execution-proof-gate.md` — Status: Proposed
  - `docs/adr/README.md` — +1 line (033)
  - mkdocs build --strict: 0 warnings; CI PASS

### S-ADAPT-5b-2b: BybitExecutionAdapter + tests + ADR-032

- **S-ADAPT-5b-2b:** MERGED PR #82 -> `09c399a51929a75d03fca1c8874b95719d17acb4` (squash)
  - 4 файла, +866/−1 — Bybit adapter + tests + docs
  - `bybit.py`: BybitExecutionAdapter(CcxtExchangeAdapter) — hooks: _build_client (ccxt.bybit, defaultType=spot), _build_order_params (clientOrderId), _is_duplicate_cid (12141/170141), get_market_rules (ccxt-normalized, limits.price==None guard)
  - `test_bybit.py`: 44 tests (FakeBybitClient, protocol, constructor, place_order, dup-cid, get_market_rules, cancel/get/reconcile/balances)
  - ADR-032: §h marked IMPLEMENTED; errata S-ADAPT-5b
  - **make check:** ruff 0 · format clean · pyright 0 · pytest 1032 passed
  - **GATE L1–L6:** all confirmed via ccxt introspection

### S-ADAPT-5b-2a: _build_order_params hook + @abstractmethod

- **S-ADAPT-5b-2a:** MERGED PR #81 -> `f2c82d52b8137494d6a56cbc2f543d5e737b63dc` (squash)
  - 2 файла, +14/−3 — hook extraction + abstract marking
  - `_build_order_params` abstract hook in base; `place_order` calls `self._build_order_params(req)`
  - `get_market_rules` marked `@abstractmethod`
  - **pytest:** 988 passed (baseline不变)

### S-ADAPT-5b-1: CcxtExchangeAdapter base extraction

- **S-ADAPT-5b-1:** MERGED PR #80 -> `f3139f16cf0f25db8818517436c6b1414e65f30c` (squash)
  - 4 файла, +386/−279 — base class extraction
  - `CcxtExchangeAdapter` — shared ccxt logic (error mapping, response building, state mapping, validate/quantize delegation)
  - `BinanceExecutionAdapter(CcxtExchangeAdapter)` — thin subclass with venue-specific hooks
  - **pytest:** 988 passed (baseline不变)

### S-ADAPT-5a: duplicate-clientOrderId safety (previous session)

- **S-ADAPT-5a:** MERGED PR #79 -> `b52bdbf43cbca2a397b169802fd3e2df51d292f9` (squash)

### S-EXEC-SAFE-2b-1c: migration smoke — real up/down on 0024

- **PR #88:** MERGED `9d195d51c9f0f58a4ae9c8a93acf7aa48cbc818a` (squash)
  - 1 файл, +47/−7
  - TestMigrationSmoke: real alembic upgrade/downgrade via Operations.context
  - F-1: alembic 1.18.4 — no schema_translate_map kwarg; engine exec_options suffice
  - Inspector caches has_table — must recreate after DDL
  - 437 tests: all green

### S-EXEC-SAFE-3c: open-order count cap (per-symbol, off-by-default)

- **PR #91:** MERGED `79e9592f6a69e74bc87a7aaec23055363a4c7b99` (squash)
  - 9 файлов, +453/−4
  - D1: ExecutionConfig.proof_max_open_orders (int, default 0, CLAY_PROOF_MAX_OPEN_ORDERS)
  - D2: OpenOrdersSnapshot frozen dataclass + count_for(symbol)
  - D3: reason_codes #20 OPEN_ORDERS_SNAPSHOT_STALE, #21 OPEN_ORDERS_ABOVE_CAP
  - D4: checker #16 freshness + #17 count-cap (LIMIT/STOP_LIMIT only, MARKET bypass)
  - D5: gate + bootstrap wiring (double-off: 0 get_open_orders при обоих off)
  - D6: ADR-033 §3 landed, errata, Status → Implemented, portfolio class closed
  - D7: 9 checker + 1 Hypothesis + 3 gate tests (475 total, +13)
  - ruff 0 · pyright 0 · pytest 475 · mkdocs --strict 0
  - Frontend flaky re-run (known, App.test.tsx:1477)

## In Progress

- **S-LIVE-4** — открытие live mode через from_env (разрешение mode-coercion)
- **First controlled `--apply` vault->Notion** — Emma настраивает Notion integration
- **Frontend flaky** (`App.test.tsx:1477`: session lifecycle flaky) — симптом, не блокер (re-run проходит)

## Baseline

| Метрика | Значение |
|---------|----------|
| **HEAD (clay main)** | `79e9592f6a69e74bc87a7aaec23055363a4c7b99` |
| **PR open** | нет |
| **CI** | ✅ 51 PR merged total |
| **pytest** | 475 passed (execution+api+db) |
| **Adapter layer** | CcxtExchangeAdapter base + BinanceAdapter + BybitAdapter + cutover + resilience wrapper + CB — complete |
| **Execution safety** | notional ✅, LiveExecutionClient ✅, degraded killswitch ✅, D9 matrix ✅, testnet-probe ✅, reconcile-before-retry ✅, circuit breaker ✅, dup-cid safety ✅, proof-gate ✅, portfolio ✅ |
| **ADR** | 032 accepted + errata; 033 Implemented (portfolio class closed) |

## Next Step

S-LIVE-4 (открытие live mode) или Emma выбирает направление.
