# ADR-034: Unknown Resolver + Durable Halt Latch

## Status

Accepted

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

### FATAL→Halt Wiring (D5)

When `ReconcileReport.has_fatal` is True (ILLEGAL_DRIFT, VENUE_ORPHAN, or age-escalated UNKNOWN), the halt-latch is engaged.

**Scope:** Broad-halt (global), not narrow per-symbol.

**Exception:** Cancel/reduce operations are allowed even in HALTED mode (ADR-033 §4).

## Consequences

### Positive
- UNKNOWN projections are resolved automatically (or escalated to FATAL)
- FATAL mismatches halt execution (fail-closed)
- Restart-safe: latch persists across restarts
- Audit trail: all transitions logged

### Negative
- Additional complexity in reconcile pipeline
- Manual intervention required to recover from halt
- Potential for false-positive halts on transient venue issues

## Implementation

- `clay.execution.ledger.unknown_resolver.UnknownResolver`
- `clay.execution.ledger.halt_latch.HaltLatchRepository`
- `clay.execution.ledger.fatal_halt.FatalHaltWiring`
- `clay.db.models_orders.HaltLatch` (migration 0028)

## Testing

- Unit tests for each component
- Integration tests for halt-latch lifecycle
- Tests for age-escalation and transition-gated audit
