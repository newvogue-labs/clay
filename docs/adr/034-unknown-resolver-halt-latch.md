# ADR-034: Unknown Resolver + Durable Halt Latch

## Status

Accepted (D-15: enforcement wiring complete)

## Context

The order ledger reconciliation circuit (D-12) has a gap: UNKNOWN/SUBMITTING projections can persist indefinitely without resolution. Additionally, FATAL mismatches are signal-only with no mechanism to halt execution.

## Decision

### Unknown Resolver (D3)

A bounded-poll resolver that transitions UNKNOWN/SUBMITTING projections to observed states by polling venue truth.

**Key properties:**
- READ-ONLY: never submits or resubmits orders
- Bounded budget: `unknown_resolve_max_polls` (default 3)
- Fixed backoff between polls
- Age escalation: `unknown_escalation_seconds` (default 3600s) → FATAL
- Self-loop: UNKNOWN → UNKNOWN is legal (persistent between ticks)

### Durable Halt Latch (D4)

A singleton row in `ops.halt_latch` table that persists across restarts.

**Key properties:**
- Fail-closed: latch engaged → SessionMode.HALTED → place denied globally
- Manual reset only: operator action required, audit-logged
- Clean reconcile tick does NOT disengage latch
- SQLite-portable: select-then-upsert pattern
- Restart-safe: persists across engine dispose/reconnect (verified by file-based SQLite test)

### FATAL→Halt Wiring (D5) — now ENFORCED (D-15)

When `ReconcileReport.has_fatal` is True (ILLEGAL_DRIFT, VENUE_ORPHAN, or age-escalated UNKNOWN), the halt-latch is engaged.

**Scope:** Broad-halt (global), not narrow per-symbol.

**Exception:** Cancel/reduce operations are allowed even in HALTED mode (ADR-033 §4).

**D-15 enforcement wiring:**
- **Flag:** `CLAY_PROOF_ENFORCE_HALT_LATCH` (requires `CLAY_PROOF_ENFORCE_SESSION=1`)
- **Probe:** `halt_probe.py::build_halt_latch_mode_probe` → `SessionMode.HALTED` when latch engaged
- **Wiring sites:**
  - `bootstrap.py`: late-binds probe into `ExecutionProofGate` (flag-gated, byte-identical when OFF)
  - `reconcile_job.py`: `fatal_halt_wiring` param → `on_fatal_report` on each fatal pair
  - `startup_reconciliation.py`: `fatal_halt_wiring` param → `on_fatal_report` + `on_escalated_fatal`
  - `lifespan.py`: builds `FatalHaltWiring` when `proof_enforce_halt_latch` is ON

## Consequences

### Positive
- UNKNOWN projections are resolved automatically (or escalated to FATAL)
- FATAL mismatches halt execution (fail-closed, enforced via proof-gate)
- Restart-safe: latch persists across restarts
- Audit trail: all transitions logged
- Default-OFF: live path byte-identical when flags are OFF

### Negative
- Additional complexity in reconcile pipeline
- Manual intervention required to recover from halt
- Potential for false-positive halts on transient venue issues

## Implementation

- `clay.execution.ledger.unknown_resolver.UnknownResolver`
- `clay.execution.ledger.halt_latch.HaltLatchRepository`
- `clay.execution.ledger.fatal_halt.FatalHaltWiring`
- `clay.execution.ledger.halt_probe.build_halt_latch_mode_probe` (D-15)
- `clay.db.models_orders.HaltLatch` (migration 0028)

## Testing

- Unit tests for each component
- Integration tests for halt-latch lifecycle
- Tests for age-escalation and transition-gated audit
- D-15: latch survives engine dispose (file-based SQLite)
- D-15: halt_probe returns HALTED/NORMAL correctly
- D-15: reconcile_job wiring integration
- D-15: bootstrap flag-gated wiring
- D-15: startup_reconciliation wiring integration
