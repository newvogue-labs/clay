# Текущее состояние Clay

## Завершено (предыдущие сессии)

...

## Завершено (текущая сессия — 2026-07-16/17)

### S-EXEC-SAFE-4b: decoupled SessionMode (NORMAL/REDUCING/HALTED)

- **PR #95:** MERGED `a5c27daa86e3e20e27d70c2518a7ef31c07e6ea0` (squash)
  - 7 файлов, +351/−4
  - D1: SessionMode(StrEnum) + mode field in SessionSnapshot
  - D2: reason_codes #23 SESSION_HALTED, #24 SESSION_REDUCE_ONLY (append-only)
  - D3: checker invariants #19 HALTED + #20 REDUCING
  - D4: gate session_mode_probe + set_session_mode_probe (off-by-default)
  - D5: bootstrap.py zero diff
  - D6: ADR-033 §3 session-bullet + errata
  - D7: 10 checker + 7 gate + 1 Hypothesis = 17 new tests
  - ruff 0 · format clean · mkdocs --strict 0 · pytest 1148 passed

### S-EXEC-SAFE-4c: session risk-tripped (drawdown + cooldown)

- **PR #96:** MERGED `70119e9a86e3e20e27d70c2518a7ef31c07e6ea0` (squash)
  - 7 файлов, +327/−4
  - D1: reason_codes #25 SESSION_DRAWDOWN_TRIPPED, #26 SESSION_COOLDOWN_TRIPPED
  - D2: SessionSnapshot drawdown_tripped + cooldown_tripped (default False)
  - D3: checker #21 drawdown + #22 cooldown (reduce-only, mirror #20)
  - D4: gate session_risk_probe + set + fail-closed
  - D5: bootstrap.py zero diff
  - D6: ADR-033 §3 landed 4c + StoplossGuard deferred
  - D7: 11 checker + 6 gate = 17 new tests
  - ruff 0 · format clean · mkdocs --strict 0 · pytest 1165 passed

### S-EXEC-SAFE-4d: submit-rate exceeded (off-by-default, dormant)

- **PR #97:** MERGED `edf057ea86e3e20e27d70c2518a7ef31c07e6ea0` (squash)
  - 7 файлов, +233/−3
  - D1: reason_code #27 SESSION_SUBMIT_RATE_EXCEEDED (append-only)
  - D2: SessionSnapshot submit_rate_exceeded: bool = False
  - D3: checker #23 submit-rate-exceeded (reduce-only)
  - D4: gate session_submit_rate_probe + fail-closed
  - D5: bootstrap.py zero diff
  - D6: ADR-033 §3 landed 4d + errata
  - D7: 6 checker + 6 gate = 12 new tests
  - ruff 0 · format clean · mkdocs --strict 0 · pytest 1177 passed

### D-7: submit-rate probe wiring (activates dormant invariant)

- **PR #99:** MERGED `811b4852ab486c2d0655ee8b07e871a176900b5e` (squash)
  - 5 файлов, +510
  - D1: ExecutionConfig proof_submit_rate_max + proof_submit_rate_window_seconds (default 0/0 dormant)
  - D2: ProofDecisionRepository.count_admitted_since(since) — sliding-window COUNT ADMIT
  - D3: build_submit_rate_probe(session_factory, max_submits, window_seconds) — zero-arg probe
  - D4: bootstrap.py late-bind: enforce_session AND max>0 AND window>0
  - D5: double-off: enforce_session=False → probe never called, live path unchanged
  - D6: gate integration: non-reduce BUY denied, reduce SELL bypasses (checker invariant)
  - D7: 24 new tests (config + repo + probe + bootstrap + gate integration)
  - pytest 1215 passed (+24) · ruff 0 · pyright 0
  - CI: backend ✅ frontend ✅

## In Progress

- **S-LIVE-4** — открытие live mode через from_env (разрешение mode-coercion)
- **First controlled `--apply` vault->Notion** — Emma настраивает Notion integration
- **Frontend flaky** (`App.test.tsx:1477`: session lifecycle flaky) — симптом, не блокер (re-run проходит)

## Baseline

| Метрика | Значение |
|---------|----------|
| **HEAD (clay main)** | `811b4852ab486c2d0655ee8b07e871a176900b5e` |
| **PR open** | нет |
| **CI** | ✅ 57 PR merged total |
| **pytest** | 1215 passed (full suite) |
| **Adapter layer** | CcxtExchangeAdapter base + BinanceAdapter + BybitAdapter + cutover + resilience wrapper + CB — complete |
| **Execution safety** | notional ✅, LiveExecutionClient ✅, degraded killswitch ✅, D9 matrix ✅, testnet-probe ✅, reconcile-before-retry ✅, circuit breaker ✅, dup-cid safety ✅, proof-gate ✅, portfolio ✅, kill-switch ✅, session-class ✅ |
| **Proof-Gate session class** | #18 kill-switch ✅ · #19 HALTED ✅ · #20 REDUCING ✅ · #21 drawdown ✅ · #22 cooldown ✅ · #23 submit-rate ✅ — **CLOSED** |
| **ADR** | 032 accepted + errata; 033 Implemented (portfolio class closed, session class closed) |
| **reason_codes** | 27 (append-only, first 22 untouched since inception) |

## Next Step

S-LIVE-4 (открытие live mode) или Emma выбирает направление.
