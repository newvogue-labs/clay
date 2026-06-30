> **STATUS: HISTORICAL PLANNING (заморожен).** План относится к этапу планирования (апрель 2026) и сохраняется как исторический контекст.
> Источник истины — `blueprint-v1.md`, `release-gates.md`, ADR (`docs/adr/`) и код (`backend/`).
> Namespace в тексте — планировочный (`clay_mc`, `app/backend`); реальный код использует `clay` / `backend`.

# E6 Signal Lifecycle, Ranking And Risk-Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working `E6` signal engine for `CLAY Mission Control`: canonical signal schema, ranking inputs, lifecycle transitions, confidence degradation, risk triggers, strategy proposals, and UI-facing contracts for the `Trading Workspace`.

**Architecture:** The implementation extends the provisional `E1` repository with a `signals` domain across backend and frontend. Backend services own signal summaries, expanded explanations, revision-safe risk snapshots, ranking logic, lifecycle transitions, and risk-trigger responses. Frontend workspace modules consume these contracts as backend truth instead of inventing ranking or lifecycle state locally. `E6` stays downstream of `E5` orchestration outputs and upstream of `E7` session discipline.

**Tech Stack:** React 19, TypeScript 5.x, Vite, React Router, Zustand, TanStack Query, FastAPI, Pydantic v2, pytest, Vitest, Testing Library, Playwright, Server-Sent Events

---

## Repository Root

This plan assumes the working application repository will live at:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app`

Important:

- this remains a `provisional implementation layout`;
- a later structural refactor is still allowed after demo validation;
- until then, keep signal truth in backend contracts, not in vibes, browser state, or lucky packet ordering.

## File Structure

### Backend

- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/signals.py`
- Create: `backend/src/clay_mc/api/routes/risk.py`
- Create: `backend/src/clay_mc/api/routes/strategy.py`
- Create: `backend/src/clay_mc/api/routes/signals_stream.py`
- Create: `backend/src/clay_mc/signals/models.py`
- Create: `backend/src/clay_mc/signals/ranking.py`
- Create: `backend/src/clay_mc/signals/lifecycle.py`
- Create: `backend/src/clay_mc/signals/risk_engine.py`
- Create: `backend/src/clay_mc/signals/strategy_proposals.py`
- Create: `backend/src/clay_mc/signals/service.py`
- Create: `backend/src/clay_mc/signals/streaming.py`
- Create: `backend/tests/api/test_signals_api.py`
- Create: `backend/tests/api/test_signals_stream.py`
- Create: `backend/tests/signals/test_signal_models.py`
- Create: `backend/tests/signals/test_ranking.py`
- Create: `backend/tests/signals/test_lifecycle.py`
- Create: `backend/tests/signals/test_risk_engine.py`

### Frontend

- Modify: `frontend/src/types/workspace.ts`
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/components/active-signals-panel.tsx`
- Modify: `frontend/src/features/workspace/components/reasoning-panel.tsx`
- Modify: `frontend/src/features/workspace/components/risk-panel.tsx`
- Create: `frontend/src/features/workspace/components/strategy-proposal-card.tsx`
- Create: `frontend/src/features/workspace/components/signal-state-chip.tsx`
- Create: `frontend/src/features/workspace/components/conflict-notice.tsx`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`
- Create: `frontend/src/features/workspace/signal-contracts.test.ts`
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`

### Repo-level

- Modify: `README.md`

---

### Task 1: Establish Signal, Risk, And Strategy Contracts

**Files:**
- Create: `backend/src/clay_mc/signals/models.py`
- Modify: `frontend/src/types/workspace.ts`
- Create: `backend/tests/signals/test_signal_models.py`
- Create: `frontend/src/features/workspace/signal-contracts.test.ts`

- [ ] **Step 1: Write the failing contract tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/signals/test_signal_models.py
from clay_mc.signals.models import SignalSummaryRecord


def test_signal_summary_record_contains_rank_confidence_and_state() -> None:
    signal = SignalSummaryRecord.model_validate(
        {
            "signal_id": "sig-1",
            "pair": "BTCUSDT",
            "direction": "long",
            "state": "active",
            "confidence": 0.84,
            "timeframe": "15m",
            "entry_summary": "70200-70300",
            "target_summary": "71100",
            "stop_summary": "69880",
            "last_updated_at": "2026-04-15T10:00:00Z",
            "rank": 1,
            "actionability": "normal",
        }
    )

    assert signal.rank == 1
    assert signal.state == "active"
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/signal-contracts.test.ts
import { describe, expect, it } from 'vitest'
import type { WorkspaceSignalSummary } from '../../types/workspace'

describe('signal contracts', () => {
  it('defines the minimum ranked signal card shape', () => {
    const signal: WorkspaceSignalSummary = {
      signalId: 'sig-1',
      pair: 'BTCUSDT',
      direction: 'long',
      state: 'active',
      confidence: 0.84,
      timeframe: '15m',
      entrySummary: '70200-70300',
      targetSummary: '71100',
      stopSummary: '69880',
      rank: 1,
      lastUpdatedAt: '2026-04-15T10:00:00Z',
      actionability: 'normal',
    }

    expect(signal.actionability).toBe('normal')
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/signals/test_signal_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test signal-contracts.test.ts --run
```

Expected: FAIL because the `signals` contracts do not exist yet.

- [ ] **Step 3: Implement shared signal contracts**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/signals/models.py
from pydantic import BaseModel


class SignalSummaryRecord(BaseModel):
    signal_id: str
    pair: str
    direction: str
    state: str
    confidence: float
    timeframe: str
    entry_summary: str
    target_summary: str
    stop_summary: str
    last_updated_at: str
    rank: int | None
    actionability: str
    invalidation_reason: str | None = None


class RiskSnapshotRecord(BaseModel):
    pair: str
    risk_posture: str
    max_drawdown_estimate: float
    position_size_hint: str
    risk_reward_hint: str
    defensive_constraints: list[str]
    actionability: str
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/types/workspace.ts
export interface WorkspaceSignalSummary {
  signalId: string
  pair: string
  direction: 'long' | 'short'
  state: 'active' | 'weakening' | 'invalidated' | 'expired' | 'absent'
  confidence: number
  timeframe: string
  entrySummary: string
  targetSummary: string
  stopSummary: string
  rank: number | null
  lastUpdatedAt: string
  actionability: 'normal' | 'reduced' | 'blocked'
  invalidationReason?: string | null
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/signals/test_signal_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test signal-contracts.test.ts --run
```

Expected: PASS with `E6` contracts available to backend and frontend.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/signals frontend/src/types/workspace.ts backend/tests/signals frontend/src/features/workspace/signal-contracts.test.ts
git commit -m "feat: add e6 signal and risk contracts"
```

### Task 2: Build Ranking And Lifecycle Engine

**Files:**
- Create: `backend/src/clay_mc/signals/ranking.py`
- Create: `backend/src/clay_mc/signals/lifecycle.py`
- Create: `backend/tests/signals/test_ranking.py`
- Create: `backend/tests/signals/test_lifecycle.py`

- [ ] **Step 1: Write the failing ranking and lifecycle tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/signals/test_ranking.py
from clay_mc.signals.ranking import rank_signal_candidates


def test_rank_signal_candidates_penalizes_conflict_and_stale_inputs() -> None:
    ranked = rank_signal_candidates(
        [
            {"signal_id": "sig-1", "base_score": 0.9, "risk_penalty": 0.1, "conflict_penalty": 0.0, "freshness_penalty": 0.0},
            {"signal_id": "sig-2", "base_score": 0.92, "risk_penalty": 0.05, "conflict_penalty": 0.2, "freshness_penalty": 0.15},
        ]
    )

    assert ranked[0]["signal_id"] == "sig-1"
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/signals/test_lifecycle.py
from clay_mc.signals.lifecycle import transition_signal_state


def test_transition_signal_state_moves_to_weakening_before_invalidation() -> None:
    weakening = transition_signal_state("active", confidence=0.42, hard_invalidated=False, ttl_expired=False)
    invalidated = transition_signal_state("weakening", confidence=0.10, hard_invalidated=True, ttl_expired=False)

    assert weakening == "weakening"
    assert invalidated == "invalidated"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/signals/test_ranking.py tests/signals/test_lifecycle.py -v
```

Expected: FAIL because ranking and lifecycle helpers do not exist yet.

- [ ] **Step 3: Implement ranking and lifecycle helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/signals/ranking.py
def rank_signal_candidates(candidates: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    scored = []
    for candidate in candidates:
        total = (
            float(candidate["base_score"])
            - float(candidate["risk_penalty"])
            - float(candidate["conflict_penalty"])
            - float(candidate["freshness_penalty"])
        )
        scored.append({**candidate, "total_score": total})
    return sorted(scored, key=lambda item: float(item["total_score"]), reverse=True)
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/signals/lifecycle.py
def transition_signal_state(
    current_state: str,
    confidence: float,
    hard_invalidated: bool,
    ttl_expired: bool,
) -> str:
    if ttl_expired:
        return "expired"
    if hard_invalidated:
        return "invalidated"
    if confidence < 0.5 and current_state == "active":
        return "weakening"
    return current_state
```

- [ ] **Step 4: Run the tests and add `absent` coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/signals/test_ranking.py tests/signals/test_lifecycle.py -v
```

Expected: PASS. Then add lifecycle coverage for `expired` and `absent`, plus ranking coverage where a strong signal is blocked by severe risk.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/signals backend/tests/signals/test_ranking.py backend/tests/signals/test_lifecycle.py
git commit -m "feat: add signal ranking and lifecycle engine"
```

### Task 3: Build Risk Engine And Strategy Proposal Logic

**Files:**
- Create: `backend/src/clay_mc/signals/risk_engine.py`
- Create: `backend/src/clay_mc/signals/strategy_proposals.py`
- Create: `backend/tests/signals/test_risk_engine.py`

- [ ] **Step 1: Write the failing risk engine tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/signals/test_risk_engine.py
from clay_mc.signals.risk_engine import evaluate_risk_trigger


def test_evaluate_risk_trigger_blocks_signal_for_stale_market_data() -> None:
    result = evaluate_risk_trigger(
        trigger_type="stale_data",
        severity="critical",
        context={"market_stale": True},
    )

    assert result["response_action"] == "block_signal"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/signals/test_risk_engine.py -v
```

Expected: FAIL because the risk engine does not exist yet.

- [ ] **Step 3: Implement risk and strategy helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/signals/risk_engine.py
def evaluate_risk_trigger(trigger_type: str, severity: str, context: dict[str, object]) -> dict[str, object]:
    if trigger_type == "stale_data" and severity == "critical":
        return {"response_action": "block_signal", "actionability": "blocked"}
    if trigger_type == "model_conflict":
        return {"response_action": "lower_confidence", "actionability": "reduced"}
    return {"response_action": "warning_only", "actionability": "normal"}
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/signals/strategy_proposals.py
def build_strategy_proposal(current_mode: str, proposed_mode: str, reason_summary: str) -> dict[str, object]:
    return {
        "proposal_id": "proposal-1",
        "current_mode": current_mode,
        "proposed_mode": proposed_mode,
        "reason_summary": reason_summary,
        "confidence_impact": -0.12,
        "requires_confirmation": True,
    }
```

- [ ] **Step 4: Run the tests and add defensive-switch coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/signals/test_risk_engine.py -v
```

Expected: PASS. Then add coverage showing repeated poor signals or overheating can produce a `switch_to_defensive` outcome and an operator-visible strategy proposal.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/signals backend/tests/signals/test_risk_engine.py
git commit -m "feat: add risk engine and strategy proposals"
```

### Task 4: Build Signals, Risk, And Strategy APIs Plus Streams

**Files:**
- Create: `backend/src/clay_mc/api/routes/signals.py`
- Create: `backend/src/clay_mc/api/routes/risk.py`
- Create: `backend/src/clay_mc/api/routes/strategy.py`
- Create: `backend/src/clay_mc/api/routes/signals_stream.py`
- Create: `backend/src/clay_mc/signals/service.py`
- Create: `backend/src/clay_mc/signals/streaming.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/api/test_signals_api.py`
- Create: `backend/tests/api/test_signals_stream.py`

- [ ] **Step 1: Write the failing API and stream tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_signals_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_signals_endpoint_returns_ranked_items() -> None:
    client = TestClient(app)

    response = client.get("/signals")

    assert response.status_code == 200
    assert len(response.json()["items"]) > 0


def test_strategy_proposals_endpoint_returns_operator_visible_proposals() -> None:
    client = TestClient(app)

    response = client.get("/strategy/proposals")

    assert response.status_code == 200
    assert response.json()["items"][0]["requires_confirmation"] is True
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_signals_stream.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_signals_stream_returns_event_stream_response() -> None:
    client = TestClient(app)

    response = client.get("/signals/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_signals_api.py tests/api/test_signals_stream.py -v
```

Expected: FAIL because the signal APIs and stream do not exist yet.

- [ ] **Step 3: Implement routes and streaming**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/signals.py
from fastapi import APIRouter


router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
def get_signals() -> dict[str, object]:
    return {
        "items": [
            {
                "signalId": "sig-1",
                "pair": "BTCUSDT",
                "direction": "long",
                "state": "active",
                "confidence": 0.84,
                "timeframe": "15m",
                "entrySummary": "70200-70300",
                "targetSummary": "71100",
                "stopSummary": "69880",
                "rank": 1,
                "lastUpdatedAt": "2026-04-15T10:00:00Z",
                "actionability": "normal",
            }
        ]
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/signals_stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/signals", tags=["signals-stream"])


def event_lines():
    yield "event: signal_update\n"
    yield 'data: {"signalId":"sig-1","state":"weakening","confidence":0.42}\n\n'


@router.get("/stream")
def get_signals_stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream")
```

- [ ] **Step 4: Run the tests and add risk event coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_signals_api.py tests/api/test_signals_stream.py -v
```

Expected: PASS. Then extend routes for `GET /risk/active`, `GET /strategy/proposals`, and risk/strategy event feeds aligned with the `E6` spec.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api backend/src/clay_mc/signals backend/tests/api/test_signals_api.py backend/tests/api/test_signals_stream.py
git commit -m "feat: add signals api and stream"
```

### Task 5: Wire E6 Contracts Into Trading Workspace UI

**Files:**
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/components/active-signals-panel.tsx`
- Modify: `frontend/src/features/workspace/components/reasoning-panel.tsx`
- Modify: `frontend/src/features/workspace/components/risk-panel.tsx`
- Create: `frontend/src/features/workspace/components/strategy-proposal-card.tsx`
- Create: `frontend/src/features/workspace/components/signal-state-chip.tsx`
- Create: `frontend/src/features/workspace/components/conflict-notice.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`

- [ ] **Step 1: Write the failing workspace rendering tests**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/trading-workspace-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TradingWorkspaceRoute } from './trading-workspace-route'

describe('TradingWorkspaceRoute E6 integrations', () => {
  it('renders signal state, risk actionability, and strategy proposal sections', () => {
    render(<TradingWorkspaceRoute />)

    expect(screen.getByText(/Signal state/i)).toBeInTheDocument()
    expect(screen.getByText(/Risk Assessment/i)).toBeInTheDocument()
    expect(screen.getByText(/Strategy Proposal/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: FAIL because the workspace has not been wired to `E6` signal/risk contracts yet.

- [ ] **Step 3: Implement E6-aware workspace components**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/components/signal-state-chip.tsx
type Props = {
  state: 'active' | 'weakening' | 'invalidated' | 'expired' | 'absent'
}

export function SignalStateChip({ state }: Props) {
  return <span>Signal state: {state}</span>
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/components/strategy-proposal-card.tsx
export function StrategyProposalCard() {
  return (
    <section>
      <h2>Strategy Proposal</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/components/conflict-notice.tsx
export function ConflictNotice() {
  return <div>Conflict Summary</div>
}
```

- [ ] **Step 4: Run the tests and add weakened/invalidated coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: PASS. Then add UI coverage proving `weakening`, `invalidated`, and `blocked` states render differently and do not look like normal actionable mode.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/features/workspace frontend/src/api/workspace-client.ts frontend/src/stores/workspace-store.ts
git commit -m "feat: wire e6 signal lifecycle into workspace"
```

### Task 6: Add End-To-End Coverage For Ranking, Lifecycle, And Risk Visibility

**Files:**
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Write the failing end-to-end tests**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/tests/e2e/trading-workspace.spec.ts
import { expect, test } from '@playwright/test'

test('weakening signal is visible as reduced, not normal mode', async ({ page }) => {
  await page.goto('/trading')

  await expect(page.getByText(/Signal state: weakening/i)).toBeVisible()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: FAIL because end-to-end `E6` state rendering is not complete yet.

- [ ] **Step 3: Implement the missing state hooks and docs updates**

```md
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/README.md
## E6 Signal Engine

- `GET /signals` returns ranked signal summaries
- `GET /risk/active` returns active risk triggers and response actions
- `GET /strategy/proposals` returns operator-visible strategy proposals
- `GET /signals/stream` pushes signal lifecycle changes

Signals are analyst-support artifacts, not execution commands.
```

- [ ] **Step 4: Run the tests and add mismatch coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: PASS. Then add end-to-end coverage for signal/risk mismatch warnings and blocked actionability rendering.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/tests/e2e/trading-workspace.spec.ts README.md
git commit -m "feat: finalize e6 signal lifecycle coverage"
```

## Spec Coverage Check

- Signal schema and UI-facing signal/risk contracts are covered by Tasks 1 and 5.
- Ranking logic and lifecycle transitions are covered by Task 2.
- Risk triggers and strategy proposals are covered by Task 3.
- `HTTP + SSE` routes for signal/risk/strategy surfaces are covered by Task 4.
- Workspace visibility for `weakening`, `invalidated`, `blocked`, conflict, and strategy proposals is covered by Tasks 5 and 6.

## Assumptions

- `E3` and `E5` remain the canonical upstream sources for workspace and orchestration semantics.
- Strategy proposals stay operator-reviewed and do not silently alter runtime behavior.
- The route and file structure remain provisional until later demo-stage cleanup.

## Execution Handoff

Plan complete and saved to `implementation_plans/e6-signal-lifecycle-ranking-and-risk-control-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
