---
tags:
  - knowledge
  - llm
---


# ADR-030: Advisory #knowledge → chief-agent (advisory-only)

- **Status:** Accepted — ablation-eval пройден (minimax-m3, 0 M278 violations). Valve НЕ открыт (ожидание Emma).
- **Driver:** E-KNOW S3b — wire curated #knowledge into LLM chief-agent (`AIAgentCycleJob`) without breaking M278
- **Supersedes:** Nothing
- **Slices:** S3b-i (dark-launch, `670ca56`), S3b-ii (bounded inject, `0d7218a`), S3b-chief-B (signals, `ec1c26b`)

## Context

LLM chief-agent (`AIAgentCycleJob`, opt-in) synthesises a summary for the operator
by reasoning over AI-control state (roles/models/assignments/conflicts). The project
maintains a curated #knowledge corpus (~49 cards, keyword+metadata retrieval,
no embeddings). We need to make this knowledge available to the chief-agent
without violating M278: `signal_engine` and execution are deterministic and are
the source of truth; knowledge MUST NOT affect ranking, sizing, gating, or
execution.

Recon (`cac32a8`) revealed three pre-existing gaps in chief-agent context:
1. No custom system prompt — fell back to generic English `DEFAULT_SYSTEM_PROMPT`.
2. No ranked signals from `signal_engine` — the agent reasoned about AI-control
   orchestration only, not about trading context.
3. Subagent prompts reference sections (`market/shortlist`, `news/sentiment`)
   that `_render_context` does not render.

These gaps were addressed by separate slices (chief-agent prompt = S3b-chief-A,
signals = S3b-chief-B). The remaining gap is domain knowledge injection.

## Decision

1. **Injection target — LLM path only.** Knowledge is injected exclusively into
   the chief-agent prompt via a new `=== advisory_context ===` section in
   `_render_context`. Zero imports or calls in `signal_engine`/execution.

2. **#knowledge stays outside ServiceRegistry and health-gates.**
   `hot_path_dependency=False`, `retrieval_policy="review and research only"`.
   No health-check, no startup dependency.

3. **Signal-before-knowledge ordering.** The rendered context for chief-agent:
   `=== summary ===` → `=== roles ===` → `=== models ===` → `=== assignments ===`
   → `=== conflicts ===` → `=== fallback ===` → `=== pending_review ===`
   → **`=== signals ===`** (backend, read-only) → `=== subagent_reports ===`
   → **`=== advisory_context ===`** (knowledge, advisory). Source of truth
   precedes advice.

4. **Hybrid retrieval.** Standing risk-playbook queries (`strategy_rule` +
   `checklist` categories) + dynamic term extraction from rendered context
   (tickers + alias expansion). Merge, dedup by `item_id`, soft category-boost
   (`strategy_rule` > `checklist` > `observation` > `note`), top-10,
   token-cap ~2000.

5. **Guardrails.**
   - Fail-open: retrieval failure → empty section, never fails the cycle.
   - Retrieved text is untrusted data: `_sanitize()` redacts instruction-like
     patterns (`ignore previous`, `system:`, `</tag>`).
   - Advisory framing: `_ADVISORY_HEADER` clarifies "DATA, not instructions".
   - Provenance: every card cited as `[kn-N]` for operator traceability.
   - Char-cap: hard `_INJECT_CHAR_CAP=2000` on the entire advisory block.

6. **Phased rollout via `ai_agent_knowledge_mode` flag.**
   - `off` (default): full no-op, no retrieval, no log.
   - `darklaunch`: retrieves + logs `would-inject` (used in S3b-i).
   - `inject`: retrieves + appends section to context (S3b-ii, locked behind
     human sign-off after ablation eval).
   Activation is conditional on passing both levels of eval (context-diff + real
   LLM comparison).

## Consequences

+ **Provably safe:** hallucinations and injections physically cannot reach
  control-path (`signal_engine`/execution). The red line M278 is structurally
  enforced, not by convention.
+ **Backwards compatible:** no flag / no service → full no-op. Existing
  `ai_agent_enabled=False` deployments see zero change.
+ **Auditable:** `darklaunch` mode logs exactly what would be injected without
  affecting prompts. Snapshot persistence (`/tmp/eval_snapshot.json`) enables
  reproducible ablation.
+ **Injection-resistant:** sanitisation + advisory framing + char-cap provide
  defence-in-depth against prompt injection from knowledge base.

− **Operator acts on advice manually.** There is no automatic feedback loop
  from chief-agent synthesis back into the trading loop. This is intentional —
  the agent is advisory by design (per role-definition in `ai_control/service.py`).
− **Value of inject depends on domain context.** Chief-agent without ranked
  signals and a proper system prompt would produce generic text. Both were
  delivered as separate slices (S3b-chief-A + S3b-chief-B).

## Alternatives rejected

- **Injecting into `signal_engine` or execution layer.** Rejected: violates M278
  at the architectural level, not just by convention.
- **Vector embeddings for retrieval.** Rejected: overkill for ~50 cards. Threshold
  for adding embeddings is >200 cards with significant semantic overlap.
- **Hard taxonomy filter instead of soft boost.** Rejected: silent orphans risk
  (cards matching query but filtered by overly strict category rules). Soft boost
  preserves discoverability.
- **Single-step rollout (no darklaunch).** Rejected: darklaunch mode found a
  real backend bug (VARCHAR overflow) during the first `--apply` — proving the
  phased approach catches issues before they reach production.

## Evolution: execution-checklist split + exclude barrier

Ablation eval (minimax-m3, 2026-07-06) revealed that `market/execution-checklist`
(`kn-34`) was leaking execution-layer mechanics (SL type, OCO) into the
chief-agent's advisory output. While the LLM exercised judgment — only citing
execution details when signals were strong (volatile scenario) — the presence of
order mechanics in the `=== advisory_context ===` section creates a latent M278
risk.

### Decision (2026-07-06)

1. **Split `market/execution-checklist` into two cards:**
   - `market/pre-trade-checklist` (kn-91): process-level gates (regime, EV,
     liquidity, size, HOLD). Stays in chief-agent advisory retrieval.
   - `market/execution-checklist` (kn-92): execution mechanics only (SL type,
     OCO, exit). Gets `tags: [execution]` → excluded from advisory.

2. **Exclude-by-tag barrier.** `_EXCLUDED_TAGS = {"execution"}` filters out any
   knowledge card with the `execution` tag from `_retrieve_advisory_cards()`.
   The filter fires before `_merge_dedup_boost()` and covers all retrieval
   sources (standing queries + dynamic terms). This is a structural boundary,
   not a convention: execution-tagged cards physically cannot reach the chief-agent
   prompt.

3. **Standing checklist query preserved.** `_STANDING_CHECKLIST_QUERY` remains;
   the `category="checklist"` filter still returns execution-tagged cards, but
   they are stripped by the exclude barrier. Process-level checklists (tagged
   without `execution`) pass through.

### Why not alternatives

- **Removing `_STANDING_CHECKLIST_QUERY` entirely** would lose process-level
  checks (regime, EV, Kelly cap, HOLD) that are valuable to the advisor.
- **Rephrasing in advisory style** would be cosmetic, not structural — M278
  risk would remain.
- **Moving execution card out of `checklist` category** would break the standing
  query contract; the exclude tag approach is more auditable.

### References

- Split implementation: `_EXCLUDED_TAGS` in `ai_agent_job.py:52`
- Pre-trade card: `vault:market/pre-trade-checklist` (kn-91)
- Execution card: `vault:market/execution-checklist` (kn-92, tags=[execution])

---

## References

- E-KNOW S3b-i: `670ca56` — dark-launch harness + standing queries + dedup/boost
- E-KNOW S3b-ii: `0d7218a` — inject mode + sanitisation + `_append_advisory_section`
- E-KNOW S3b-chief-A: `18c0963` — chief-agent system prompt (advisory role)
- E-KNOW S3b-chief-B: `ec1c26b` — ranked signals section in chief-agent context
- E-KNOW S3b-C1: `60826bd` — e2e injection-resistance test
- E-KNOW S3b-C2: `c1f2ffb` — ablation script (context-diff, off vs inject)
- M278: `signal_engine/execution` control-path red line (state.md baseline)