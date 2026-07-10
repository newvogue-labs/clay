---
tags:
  - llm
---

# ADR-017: Homogeneous role registry (gemma-4-31b as chief-eligible)

- **Status:** Proposed (2026-06-21)
- **Driver:** Demo pipeline validation (S4 post-close)
- **Supersedes:** Nothing (complements ADR-013)

## Context

`ai-conflict` penalty (−0.10 confidence / −0.08 ranking) gates session activation
even in normal market conditions, because a zero-penalty homogeneous configuration
with a non-toy chief is impossible:

- `chief-agent` is only compatible with `minimax-m3` (TokenRouter/MiniMax) or
  `gemma4:e2b-it-qat` (local Ollama 2B — rejected as toy for validation).
- `news-sentiment-agent` is only compatible with `gemma-4-31b` (Google AI Studio).
- `forecast-model` is only compatible with Google-family models.

This creates a structural penalty wall: at 18:17 on 2026-06-21, SOLUSDT had
`base 0.55` on the Google scanner, but −0.08 thin-context −0.10 ai-conflict
dropped it to 0.39 — below the 0.45 shortlist threshold. The market had a
setup; the penalty blocked it.

ADR-013 envisions homogeneous provider tiers. The current registry makes a
homogeneous tier with a capable chief model unachievable.

## Decision

1. Add `"chief-agent"` to `gemma-4-31b`'s `compatible_roles` in
   `_build_model_registry()`. This enables an all-Google tier:
   - chief-agent → `gemma-4-31b` (Google AI Studio, 31B)
   - market-scanner → `gemma-4-31b` (Google AI Studio)
   - news-sentiment-agent → `gemma-4-31b` (Google AI Studio)
   - forecast-model → `gemini-3.1-flash-lite` (Google)
   → 0 provider-mix conflicts → penalty legitimately 0.

2. Default assignments remain hetero (honest baseline). The homogeneous config
   is activated at runtime via the existing 2-phase commit
   (`POST /ai-control/assignments/review` + `apply`).

3. The penalty logic in `_build_conflicts()` and `_build_assignments()` is
   **NOT removed** — it continues to gate real hetero mixes. Only the registry
   constraint is relaxed.

## Rejected

- **Option B** (add `"news-sentiment-agent"`, `"forecast-model"` to `minimax-m3`):
  rejected because we don't know *why* minimax was tagged incompatible for
  these roles (likely capability fit), and moving two signal roles to a
  questionably-compatible model would corrupt the demo baseline.

## Consequences

- Positive: SOL `base 0.55 − 0.08 thin-context = 0.47 ≥ 0.45` would have
  passed shortlist at 18:17. First chevron unblocked.
- Neutral: chief drops from MiniMax-M3 to Gemma 4 31B IT. Acceptable for
  paper-demo baseline; A/B comparison possible later.
- Risk: if `gemma-4-31b` underperforms as chief (context synthesis quality),
  the demo may produce lower-quality theses. Mitigation: revert is a single
  assignment change (no deploy).
