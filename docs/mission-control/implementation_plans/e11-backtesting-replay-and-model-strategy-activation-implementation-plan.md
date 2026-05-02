# E11 Backtesting, Replay And Model/Strategy Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working `E11` validation layer for `CLAY Mission Control`: replay runs, comparison summaries, signal-quality-on-history views, activation review-cards, staged activation, and preflight-aware enablement of model/strategy candidates.

**Architecture:** The implementation extends the provisional `E1` repository with a `validation` domain across backend and frontend. Backend services own replay job orchestration, validation summaries, candidate comparison, and activation review-card staging. Frontend surfaces normalized replay and activation-review contracts without inventing local toggles or silent activation shortcuts. `E11` stays downstream of `E5`, `E6`, and `E9`, and upstream of `E12` release-readiness gates.

**Tech Stack:** React 19, TypeScript 5.x, Vite, React Router, Zustand, TanStack Query, FastAPI, Pydantic v2, pytest, Vitest, Testing Library, Playwright, Server-Sent Events

---

## Repository Root

This plan assumes the working application repository will live at:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app`

Important:

- this remains a `provisional implementation layout`;
- a later structural refactor is still allowed after demo validation;
- until then, keep replay and activation truth in backend jobs and review-card state, not in wishful toggles, heroic spreadsheets, or browser-local courage.

## File Structure

### Backend

- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/replay.py`
- Create: `backend/src/clay_mc/api/routes/validation.py`
- Create: `backend/src/clay_mc/api/routes/activation_review.py`
- Create: `backend/src/clay_mc/api/routes/replay_stream.py`
- Create: `backend/src/clay_mc/validation/models.py`
- Create: `backend/src/clay_mc/validation/replay.py`
- Create: `backend/src/clay_mc/validation/comparisons.py`
- Create: `backend/src/clay_mc/validation/activation_review.py`
- Create: `backend/src/clay_mc/validation/service.py`
- Create: `backend/src/clay_mc/validation/streaming.py`
- Create: `backend/tests/api/test_replay_api.py`
- Create: `backend/tests/api/test_validation_api.py`
- Create: `backend/tests/api/test_activation_review_api.py`
- Create: `backend/tests/api/test_replay_stream.py`
- Create: `backend/tests/validation/test_models.py`
- Create: `backend/tests/validation/test_replay.py`
- Create: `backend/tests/validation/test_comparisons.py`
- Create: `backend/tests/validation/test_activation_review.py`

### Frontend

- Modify: `frontend/src/types/workspace.ts`
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/validation/components/replay-run-card.tsx`
- Create: `frontend/src/features/validation/components/validation-summary-card.tsx`
- Create: `frontend/src/features/validation/components/comparison-card.tsx`
- Create: `frontend/src/features/validation/components/activation-review-card.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`
- Create: `frontend/src/features/validation/validation-contracts.test.ts`
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`

### Repo-level

- Modify: `README.md`

---

### Task 1: Establish Replay, Validation, And Activation Review Contracts

**Files:**
- Create: `backend/src/clay_mc/validation/models.py`
- Modify: `frontend/src/types/workspace.ts`
- Create: `backend/tests/validation/test_models.py`
- Create: `frontend/src/features/validation/validation-contracts.test.ts`

- [ ] **Step 1: Write the failing contract tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/validation/test_models.py
from clay_mc.validation.models import ActivationReviewCardRecord


def test_activation_review_card_record_contains_confirmation_and_preflight_flags() -> None:
    card = ActivationReviewCardRecord.model_validate(
        {
            "review_card_id": "card-1",
            "candidate_id": "model-v2",
            "candidate_type": "model",
            "evidence_summary": "Candidate shows stronger signal stability on replay.",
            "key_metrics": {"signal_count": 48, "invalidated_count": 6},
            "risks": ["Requires preflight before enablement"],
            "requires_preflight": True,
            "requires_confirmation": True,
        }
    )

    assert card.requires_preflight is True
    assert card.requires_confirmation is True
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/validation/validation-contracts.test.ts
import { describe, expect, it } from 'vitest'
import type { ReplayRunSummary } from '../../types/workspace'

describe('validation contracts', () => {
  it('defines the minimum replay run summary shape', () => {
    const replay: ReplayRunSummary = {
      replayId: 'replay-1',
      status: 'completed',
      timeRangeLabel: '2026-01-01 -> 2026-01-31',
      strategyVariant: 'Momentum',
      modelVariant: 'chief:gpt-5.4',
      timelineItems: [],
    }

    expect(replay.status).toBe('completed')
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/validation/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test validation-contracts.test.ts --run
```

Expected: FAIL because `E11` contracts do not exist yet.

- [ ] **Step 3: Implement shared validation contracts**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/validation/models.py
from pydantic import BaseModel


class ActivationReviewCardRecord(BaseModel):
    review_card_id: str
    candidate_id: str
    candidate_type: str
    evidence_summary: str
    key_metrics: dict[str, object]
    risks: list[str]
    requires_preflight: bool
    requires_confirmation: bool
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/types/workspace.ts
export interface ReplayRunSummary {
  replayId: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  timeRangeLabel: string
  strategyVariant: string
  modelVariant: string | null
  timelineItems: Array<{ label: string }>
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/validation/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test validation-contracts.test.ts --run
```

Expected: PASS with `E11` contracts available to backend and frontend.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/validation frontend/src/types/workspace.ts backend/tests/validation frontend/src/features/validation/validation-contracts.test.ts
git commit -m "feat: add e11 validation contracts"
```

### Task 2: Build Replay And Validation Summary Logic

**Files:**
- Create: `backend/src/clay_mc/validation/replay.py`
- Create: `backend/tests/validation/test_replay.py`

- [ ] **Step 1: Write the failing replay tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/validation/test_replay.py
from clay_mc.validation.replay import build_replay_summary


def test_build_replay_summary_tracks_invalidated_and_weakening_signals() -> None:
    summary = build_replay_summary(
        replay_id="replay-1",
        signal_count=48,
        high_confidence_count=21,
        weakening_count=9,
        invalidated_count=6,
        mismatch_count=2,
    )

    assert summary["invalidated_count"] == 6
    assert summary["weakening_count"] == 9
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/validation/test_replay.py -v
```

Expected: FAIL because replay helpers do not exist yet.

- [ ] **Step 3: Implement replay summary helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/validation/replay.py
def build_replay_summary(
    replay_id: str,
    signal_count: int,
    high_confidence_count: int,
    weakening_count: int,
    invalidated_count: int,
    mismatch_count: int,
) -> dict[str, object]:
    return {
        "summary_id": f"{replay_id}-summary",
        "replay_id": replay_id,
        "signal_count": signal_count,
        "high_confidence_count": high_confidence_count,
        "weakening_count": weakening_count,
        "invalidated_count": invalidated_count,
        "mismatch_count": mismatch_count,
        "quality_notes": [],
    }
```

- [ ] **Step 4: Run the tests and add insufficient-history coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/validation/test_replay.py -v
```

Expected: PASS. Then add coverage proving replay can fail honestly on insufficient historical basis instead of producing synthetic confidence.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/validation/replay.py backend/tests/validation/test_replay.py
git commit -m "feat: add e11 replay summary logic"
```

### Task 3: Build Comparison And Activation Review Logic

**Files:**
- Create: `backend/src/clay_mc/validation/comparisons.py`
- Create: `backend/src/clay_mc/validation/activation_review.py`
- Create: `backend/tests/validation/test_comparisons.py`
- Create: `backend/tests/validation/test_activation_review.py`

- [ ] **Step 1: Write the failing comparison and review-card tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/validation/test_comparisons.py
from clay_mc.validation.comparisons import build_candidate_comparison


def test_build_candidate_comparison_preserves_risk_notes_and_readiness() -> None:
    comparison = build_candidate_comparison(
        candidate_id="model-v2",
        candidate_type="model",
        baseline_id="model-v1",
        metric_bundle={"signal_count": 48},
        risk_notes=["Needs wider replay coverage"],
        decision_readiness="review_required",
    )

    assert comparison["decision_readiness"] == "review_required"
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/validation/test_activation_review.py
from clay_mc.validation.activation_review import build_activation_review_card


def test_build_activation_review_card_stays_staged_when_preflight_is_required() -> None:
    card = build_activation_review_card(
        candidate_id="strategy-v2",
        candidate_type="strategy",
        evidence_summary="Replay shows better consistency but config changed.",
        key_metrics={"invalidated_count": 4},
        risks=["Preflight required before activation"],
        requires_preflight=True,
    )

    assert card["requires_preflight"] is True
    assert card["requires_confirmation"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/validation/test_comparisons.py tests/validation/test_activation_review.py -v
```

Expected: FAIL because comparison and activation-review helpers do not exist yet.

- [ ] **Step 3: Implement comparison and activation-review helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/validation/comparisons.py
def build_candidate_comparison(
    candidate_id: str,
    candidate_type: str,
    baseline_id: str,
    metric_bundle: dict[str, object],
    risk_notes: list[str],
    decision_readiness: str,
) -> dict[str, object]:
    return {
        "comparison_id": "comparison-1",
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "baseline_id": baseline_id,
        "metric_bundle": metric_bundle,
        "risk_notes": risk_notes,
        "decision_readiness": decision_readiness,
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/validation/activation_review.py
def build_activation_review_card(
    candidate_id: str,
    candidate_type: str,
    evidence_summary: str,
    key_metrics: dict[str, object],
    risks: list[str],
    requires_preflight: bool,
) -> dict[str, object]:
    return {
        "review_card_id": "card-1",
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "evidence_summary": evidence_summary,
        "key_metrics": key_metrics,
        "risks": risks,
        "requires_preflight": requires_preflight,
        "requires_confirmation": True,
        "activation_state": "staged" if requires_preflight else "ready_for_confirmation",
    }
```

- [ ] **Step 4: Run the tests and add failed-preflight coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/validation/test_comparisons.py tests/validation/test_activation_review.py -v
```

Expected: PASS. Then add coverage for blocked activation when review-card is acknowledged but preflight fails.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/validation backend/tests/validation/test_comparisons.py backend/tests/validation/test_activation_review.py
git commit -m "feat: add e11 comparison and activation review logic"
```

### Task 4: Build Replay, Validation, And Activation Review APIs Plus Streams

**Files:**
- Create: `backend/src/clay_mc/api/routes/replay.py`
- Create: `backend/src/clay_mc/api/routes/validation.py`
- Create: `backend/src/clay_mc/api/routes/activation_review.py`
- Create: `backend/src/clay_mc/api/routes/replay_stream.py`
- Create: `backend/src/clay_mc/validation/service.py`
- Create: `backend/src/clay_mc/validation/streaming.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/api/test_replay_api.py`
- Create: `backend/tests/api/test_validation_api.py`
- Create: `backend/tests/api/test_activation_review_api.py`
- Create: `backend/tests/api/test_replay_stream.py`

- [ ] **Step 1: Write the failing API and stream tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_replay_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_replay_runs_endpoint_returns_structured_items() -> None:
    client = TestClient(app)

    response = client.get("/replay/runs")

    assert response.status_code == 200
    assert len(response.json()["items"]) > 0
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_replay_stream.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_replay_stream_returns_event_stream_response() -> None:
    client = TestClient(app)

    response = client.get("/replay/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_replay_api.py tests/api/test_validation_api.py tests/api/test_activation_review_api.py tests/api/test_replay_stream.py -v
```

Expected: FAIL because the `E11` routes and replay stream do not exist yet.

- [ ] **Step 3: Implement routes and streaming**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/replay.py
from fastapi import APIRouter


router = APIRouter(prefix="/replay", tags=["replay"])


@router.get("/runs")
def get_replay_runs() -> dict[str, object]:
    return {
        "items": [
            {
                "replay_id": "replay-1",
                "status": "completed",
                "time_range_label": "2026-01-01 -> 2026-01-31",
                "strategy_variant": "Momentum",
                "model_variant": "chief:gpt-5.4",
                "timeline_items": [],
            }
        ]
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/replay_stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/replay", tags=["replay-stream"])


def event_lines():
    yield "event: replay_progress\n"
    yield 'data: {"replayId":"replay-1","status":"running","progress":0.42}\n\n'


@router.get("/stream")
def get_replay_stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream")
```

- [ ] **Step 4: Run the tests and add activation-review coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_replay_api.py tests/api/test_validation_api.py tests/api/test_activation_review_api.py tests/api/test_replay_stream.py -v
```

Expected: PASS. Then extend coverage for `POST /replay/run`, `GET /validation/comparisons`, `GET /activation-review/{candidateId}`, and staged/confirm activation commands.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api backend/src/clay_mc/validation backend/tests/api/test_replay_api.py backend/tests/api/test_validation_api.py backend/tests/api/test_activation_review_api.py backend/tests/api/test_replay_stream.py
git commit -m "feat: add e11 replay and activation apis"
```

### Task 5: Wire Replay And Activation Review Surfaces Into Workspace UI

**Files:**
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/validation/components/replay-run-card.tsx`
- Create: `frontend/src/features/validation/components/validation-summary-card.tsx`
- Create: `frontend/src/features/validation/components/comparison-card.tsx`
- Create: `frontend/src/features/validation/components/activation-review-card.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`

- [ ] **Step 1: Write the failing workspace rendering tests**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/trading-workspace-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TradingWorkspaceRoute } from './trading-workspace-route'

describe('TradingWorkspaceRoute E11 integrations', () => {
  it('renders replay, validation, and activation review surfaces', () => {
    render(<TradingWorkspaceRoute />)

    expect(screen.getByText(/Replay/i)).toBeInTheDocument()
    expect(screen.getByText(/Validation Summary/i)).toBeInTheDocument()
    expect(screen.getByText(/Activation Review/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: FAIL because the workspace has not been wired to `E11` validation surfaces yet.

- [ ] **Step 3: Implement `E11`-aware validation components**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/validation/components/replay-run-card.tsx
export function ReplayRunCard() {
  return (
    <section>
      <h2>Replay</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/validation/components/validation-summary-card.tsx
export function ValidationSummaryCard() {
  return (
    <section>
      <h2>Validation Summary</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/validation/components/activation-review-card.tsx
export function ActivationReviewCard() {
  return (
    <section>
      <h2>Activation Review</h2>
    </section>
  )
}
```

- [ ] **Step 4: Run the tests and add staged-activation coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: PASS. Then add UI coverage proving staged activation and failed-preflight states remain visible and cannot be mistaken for enabled runtime state.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/features/validation frontend/src/features/workspace frontend/src/api/workspace-client.ts frontend/src/stores/workspace-store.ts
git commit -m "feat: wire e11 validation into workspace"
```

### Task 6: Add End-To-End Coverage For Replay And Activation Flow

**Files:**
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Write the failing end-to-end tests**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/tests/e2e/trading-workspace.spec.ts
import { expect, test } from '@playwright/test'

test('activation stays staged when preflight is still required', async ({ page }) => {
  await page.goto('/trading')

  await expect(page.getByText(/Activation Review/i)).toBeVisible()
  await expect(page.getByText(/preflight/i)).toBeVisible()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: FAIL because end-to-end `E11` rendering is not complete yet.

- [ ] **Step 3: Implement the missing state hooks and docs updates**

```md
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/README.md
## E11 Replay And Activation Review

- `GET /replay/runs` returns replay runs and summaries
- `GET /validation/comparisons` returns candidate comparisons
- `GET /activation-review/{candidateId}` returns activation review-card state
- `GET /replay/stream` pushes replay progress

Replay supports validation. It does not replace demo evidence, and activation never bypasses confirmation or required preflight.
```

- [ ] **Step 4: Run the tests and add failed-activation coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: PASS. Then add end-to-end coverage for replay no-history errors, comparison visibility, and blocked activation after failed preflight.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/tests/e2e/trading-workspace.spec.ts README.md
git commit -m "feat: finalize e11 replay activation coverage"
```

## Spec Coverage Check

- Replay, validation summary, comparison, and activation review-card contracts are covered by Tasks 1 and 5.
- Replay summaries and insufficient-history behavior are covered by Task 2.
- Candidate comparisons, staged activation, and review-card logic are covered by Task 3.
- `HTTP + SSE` routes for replay, validation, and activation review are covered by Task 4.
- Workspace visibility for replay, validation, staged activation, and required preflight state is covered by Tasks 5 and 6.

## Assumptions

- `E5`, `E6`, and `E9` remain the canonical upstream sources for assignments, signal semantics, and review evidence.
- Replay remains a validation tool and never becomes a substitute for demo-stage evidence.
- The route and file structure remain provisional until later demo-stage cleanup.

## Execution Handoff

Plan complete and saved to `implementation_plans/e11-backtesting-replay-and-model-strategy-activation-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
