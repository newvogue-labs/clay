---
tags:
  - execution
  - safety
  - architecture-v2
---

# ADR-033: Execution Proof-Gate

- **Status:** Implemented (per-order + portfolio invariants landed; session invariants pending)
- **Date:** 2026-07-14
- **Depends on:** ADR-032 (Exchange Execution Adapter, Multi-Venue), ADR-025 (Execution Modes & Override Gate)
- **References:** ADR-021 / ADR-029 (Session & Exposure Risk-Limits), ADR-030 & M278 (knowledge ≠ execution red line), S-LIVE-2/3/4 (notional guard, killswitch, arming)
- **Supersedes:** —

## Context

Order submission is an **irreversible side-effect**. Once a `place_order` reaches a
venue, no downstream check can undo it. This inverts the usual default: an order
is **"guilty until proven safe"** — it must pass an explicit, auditable admission
check *before* any network call.

Two forces make this ADR necessary now:

1. **Real-money horizon.** S-LIVE-4/Q5 arming is walled but approaching. A single
   consolidated admission gate must exist *before* live arming, not after.
2. **Current invariants are scattered and imperative.** Recon (M350, byte @
   `09c399a5`) found the safety surface spread across `normalization.py`,
   `adapter/notional.py`, `resilience.py`, `routes/execution.py`, `rules.py`,
   `config.py`, `domain.py`. The checks largely *exist*, but there is no single
   declarative point of admission and no complete, durable decision-record.

The value of this ADR is therefore **consolidation + declarativeness +
machine-checkability + a full audit-record**, not a new set of checks.

### What this is NOT

Proof-carrying code (PCC) / Universalis-style verified execution was evaluated
and **rejected** for the trusted, deterministic, per-order path: it is overkill,
has zero production precedent in trading, and its cost/benefit is inverted for
code we already control. Formal provers (Lean, donor #13) remain a cultural
reference only.

Automind (donor #12) stays a **future layer** aimed at an *untrusted* generator
(an LLM strategy proposing orders), which is exactly the boundary held by M278 /
ADR-030 (knowledge advises, it never controls execution).

## Decision

Introduce an **Execution Proof-Gate**: a **reference monitor** that admits or
denies every order-plane intent against a declarative invariant catalog, and
emits a **durable decision-record** for each admission decision.

### 1. Model: reference monitor + durable decision-record

- Every order-plane intent (place / cancel / modify) passes through a single
  admission function that returns **admit** or **deny(reason-codes)**.
- Each decision produces a durable record:
  - `intent_hash` — hash of the normalized order intent,
  - `snapshot_hash` + `snapshot_ts` — the market/account snapshot the decision was made against,
  - `metadata_version` — version of the venue rules / market metadata used,
  - `invariant_results` — the ordered list of invariant-ids evaluated and their outcomes,
  - `reason_codes` — stable, enumerated deny reasons (empty on admit),
  - `arming_event_id` — the arming event under which the decision was taken.
- The record is persisted to a **durable audit store outside retention** (D3).

### 2. Position in the architecture

The gate is **venue-agnostic** and sits on the adapter/resilience seam. It is the
**outermost** composition layer, evaluated *before* any side-effect:

```
ExecutionProofGate → ResilientExecutionAdapter → CcxtExchangeAdapter → venue
```

- The gate runs before reconcile-before-retry (S-ADAPT-3) and the CircuitBreaker
  (S-ADAPT-4): a denied intent never reaches resilience or the wire.
- The gate is a **consolidation layer**. It orchestrates and records existing
  checks — S-LIVE-2 notional cap (`adapter/notional.py`), ADR-021/029 session &
  exposure limits — rather than re-implementing them. New declarative wrappers
  wire those checks into the invariant catalog; their semantics do not change.

### 3. Invariant catalog (three classes)

**Per-order (deterministic, hot-path):**

- symbol allowlist + tradable status
- order type / TIF supported by venue (`MarketRules`)
- all numeric fields `Decimal`, strictly > 0
- price within min/max, aligned to tick
- quantity within min/max, aligned to step, within market caps
- notional within venue min/max
- internal max-notional hard-cap (S-LIVE-2, already implemented)
- reduce-only correctness
- stop / trigger consistency
- GTD expiry validity

**Portfolio (account-scoped):**

- free balance ≥ cost + fees + reserved (no oversell)
- projected position ≤ MAX_POSITION (per-symbol notional USDT cap, entry/increase-only; reduce/close bypass per §4)
- open-order counts within MAX_NUM_ORDERS (per-symbol resting-order count cap, all-sides, MARKET bypass, off-by-default) — **Landed** in S-EXEC-SAFE-3c (closes portfolio class)

**Session (state-scoped):**

- manual-arm present (+ break-glass), off-by-default
- HALTED → only cancel admitted; REDUCING → only position-reducing admitted
- submit / modify rate within budget
- kill-switch not engaged
- cooldown / StoplossGuard / MaxDrawdown not tripped
- no duplicate intent

**Freshness (cross-cutting invariant):**

- snapshot freshness / version is itself an invariant: a stale or
  version-mismatched snapshot ⇒ **deny** (never admit on stale state).

### 4. Separate paths: entry/increase vs reduce/close

Entry / increase and reduce / close are **distinct admission paths**. Cancels and
position-reducing orders remain admissible in HALTED / REDUCING session states, so
that a degraded system can always de-risk. Over-strict closing is treated as an
anti-pattern (see §7).

### 5. Mechanism

- **pydantic v2 strict** at ingress — reject malformed intents before evaluation.
- **Small pure fail-closed checker** on the hot-path — explicit, O(1), single point
  of admission, returns stable reason-codes.
- **icontract** — declarative pre/post specifications, enforced in CI.
- **Hypothesis** — property-based tests in CI.

Explicitly **excluded**: CrossHair (confirmed unsoundness on `Decimal`, #448,
false "Confirmed"); icontract-hypothesis (abandonware, 2021); **Z3 on the
hot-path** (CI-only, and only where non-linear reasoning is required).

### 6. Reason-codes & hot-path

Deny outcomes use a **stable, enumerated** reason-code set (append-only). The
hot-path admission is **O(1)** in the number of invariants and never performs
network I/O.

### 7. Anti-patterns → hard constraints (precedent-driven)

| Precedent | Failure mode | Constraint in this ADR |
|---|---|---|
| Knight Capital ($440M) | stale/rogue code path executed | deny = **hard-block**, kill-switch first |
| Citi ($1.4bn) | advisory warning not blocking | deny is a block, never advisory |
| ABN AMRO | control not enforced | fail-closed, single admission point |
| TOCTOU race | check-to-use gap | snapshot-versioning + reconcile |
| Spec drift | stale venue rules | metadata TTL-refresh; venue-rejection = invalidation |
| Over-strict close | cannot de-risk when degraded | separate reduce/close paths |
| Precision vs limits | conflated quantization & bounds | precision ≠ limits, checked separately |

### 8. Arming

Admission to the *live* order-plane is **hard-block, off-by-default,
fail-closed**, gated behind S-LIVE-4/Q5 with a human-in-the-loop GO. Kill-switch
takes precedence over every other invariant.

## Invariants (red lines)

1. Deny is a hard-block — never advisory.
2. Fail-closed everywhere: any evaluation error ⇒ deny.
3. No admission on stale/mismatched snapshot (freshness is an invariant).
4. Snapshot-versioning guards against TOCTOU.
5. Venue-rejection invalidates cached rules; metadata carries a TTL.
6. Precision (quantization) and limits (bounds) are distinct checks.
7. Hot-path is O(1) with stable reason-codes and zero network I/O.
8. Gate is venue-agnostic (adapter/resilience seam).
9. M278 holds: signal ≠ execution; knowledge never enters the gate's control path.

## Scope & slice decomposition

- **S-EXEC-SAFE-2** (first): per-order invariants + snapshot-freshness on a single
  venue-agnostic admission point + decision-record + reason-codes.
- **S-EXEC-SAFE-3+**: portfolio invariants (consolidating ADR-029 exposure).
- **S-EXEC-SAFE-4+**: session invariants (consolidating ADR-021, killswitch, cooldown).
- **S-EXEC-SAFE-N**: arming wiring (S-LIVE-4/Q5).

**Non-scope:** stochastic outcomes (fill / slippage / market impact / future
liquidity / stop-fill / PnL) — outside the gate by construction; PCC / Automind
(future untrusted-generator layer); Z3 on the hot-path; operator GO (Q5) — the
gate never replaces it.

## Consequences

- **+** Single declarative admission point; complete durable audit-record; existing
  scattered checks consolidated without semantic change.
- **+** Machine-checkable specs (icontract + Hypothesis) raise confidence before arming.
- **−** New composition layer to maintain; decision-record storage to manage under D3.
- **Migration:** S-LIVE-2 (`adapter/notional.py`) and ADR-021/029 risk-services are
  the first invariants wired in, not rewritten.

## Errata

- **S-EXEC-SAFE-3a:** Free-balance no-oversell invariant landed (off-by-default).
- **S-EXEC-SAFE-3b:** Position cap per-symbol landed (off-by-default).
- **S-EXEC-SAFE-3c:** Open-order count cap per-symbol landed (off-by-default, all-sides count, MARKET bypass). Closes **portfolio class** (#16/#17). ALGO/ICEBERG dropped — no such order types exist.

## Verification note (deps)

py3.14 compatibility of icontract / pydantic v2 / Hypothesis is a **lead, not
verified**. Host must byte-check against the installed versions and run the suite
on 3.14 before any "verified" status (G6).

## Open questions

- Storage shape of the decision-record (reuse existing audit table vs dedicated).
- `max_order_notional_usdt: float → Decimal` (F-4) — fold into S-EXEC-SAFE-2 or keep separate.
- Exact reason-code enumeration (frozen at S-EXEC-SAFE-2, append-only thereafter).
