> **STATUS: HISTORICAL PLANNING (заморожен).** План относится к этапу планирования (апрель 2026) и сохраняется как исторический контекст.
> Источник истины — `blueprint-v1.md`, `release-gates.md`, ADR (`docs/adr/`) и код (`backend/`).
> Namespace в тексте — планировочный (`clay_mc`, `app/backend`); реальный код использует `clay` / `backend`.

# E8 Demo Trading Integration And Result Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working `E8` demo validation layer for `CLAY Mission Control`: manual demo-trade workflow, read-only reconciliation, signal-to-trade linking, outcome tracking, readiness summary, and UI-facing result visibility without introducing hidden auto-execution.

**Architecture:** The implementation extends the provisional `E1` repository with a `demo_trading` domain across backend and frontend. Backend services own observed trade ingestion, reconciliation, signal-trade linking, outcome computation, and readiness summaries. Frontend surfaces backend truth for recent demo trades, link status, outcome visibility, and stage readiness. `E8` stays downstream of `E6` signal semantics and `E7` session discipline, and upstream of `E9` audit/review analytics.

**Tech Stack:** React 19, TypeScript 5.x, Vite, React Router, Zustand, TanStack Query, FastAPI, Pydantic v2, pytest, Vitest, Testing Library, Playwright, Server-Sent Events

---

## Repository Root

This plan assumes the working application repository will live at:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app`

Important:

- this remains a `provisional implementation layout`;
- a later structural refactor is still allowed after demo validation;
- until then, keep demo-trade truth in backend records and reconciliation logic, not in hopeful notes, browser guesses, or a clipboard-powered oracle.

## File Structure

### Backend

- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/demo_trades.py`
- Create: `backend/src/clay_mc/api/routes/demo_stage.py`
- Create: `backend/src/clay_mc/api/routes/demo_results_stream.py`
- Create: `backend/src/clay_mc/demo_trading/models.py`
- Create: `backend/src/clay_mc/demo_trading/reconciliation.py`
- Create: `backend/src/clay_mc/demo_trading/linking.py`
- Create: `backend/src/clay_mc/demo_trading/readiness.py`
- Create: `backend/src/clay_mc/demo_trading/service.py`
- Create: `backend/src/clay_mc/demo_trading/streaming.py`
- Create: `backend/tests/api/test_demo_trades_api.py`
- Create: `backend/tests/api/test_demo_stage_api.py`
- Create: `backend/tests/api/test_demo_results_stream.py`
- Create: `backend/tests/demo_trading/test_models.py`
- Create: `backend/tests/demo_trading/test_linking.py`
- Create: `backend/tests/demo_trading/test_reconciliation.py`
- Create: `backend/tests/demo_trading/test_readiness.py`

### Frontend

- Modify: `frontend/src/types/workspace.ts`
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/demo/components/demo-trade-card.tsx`
- Create: `frontend/src/features/demo/components/demo-outcome-card.tsx`
- Create: `frontend/src/features/demo/components/demo-link-status-chip.tsx`
- Create: `frontend/src/features/demo/components/demo-readiness-banner.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`
- Create: `frontend/src/features/demo/demo-contracts.test.ts`
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`

### Repo-level

- Modify: `README.md`

---

### Task 1: Establish Demo Trade, Link, And Outcome Contracts

**Files:**
- Create: `backend/src/clay_mc/demo_trading/models.py`
- Modify: `frontend/src/types/workspace.ts`
- Create: `backend/tests/demo_trading/test_models.py`
- Create: `frontend/src/features/demo/demo-contracts.test.ts`

- [ ] **Step 1: Write the failing contract tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/demo_trading/test_models.py
from clay_mc.demo_trading.models import DemoOutcomeRecord


def test_demo_outcome_record_contains_link_and_result_fields() -> None:
    outcome = DemoOutcomeRecord.model_validate(
        {
            "outcome_id": "outcome-1",
            "signal_id": "sig-1",
            "session_id": "session-1",
            "pair": "BTCUSDT",
            "outcome_status": "matched",
            "executed_at": "2026-04-15T12:00:00Z",
            "entry_delta_summary": "within expected band",
            "exit_delta_summary": None,
            "pnl_value": 14.25,
            "pnl_percent": 0.82,
            "result_notes": ["clean demo execution"],
        }
    )

    assert outcome.outcome_status == "matched"
    assert outcome.pnl_percent == 0.82
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/demo/demo-contracts.test.ts
import { describe, expect, it } from 'vitest'
import type { DemoReadinessSummary } from '../../types/workspace'

describe('demo trading contracts', () => {
  it('defines the minimum demo readiness summary shape', () => {
    const summary: DemoReadinessSummary = {
      sessionCount: 5,
      qualifiedSessionCount: 5,
      longSessionCount: 2,
      stableProfitFlag: true,
      majorDrawdownFlag: false,
      criticalTechnicalFailureFlag: false,
      cautiousLiveReady: false,
      blockingReasons: ['manual review required'],
    }

    expect(summary.longSessionCount).toBe(2)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/demo_trading/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test demo-contracts.test.ts --run
```

Expected: FAIL because `E8` contracts do not exist yet.

- [ ] **Step 3: Implement shared demo-trading contracts**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/demo_trading/models.py
from pydantic import BaseModel


class DemoOutcomeRecord(BaseModel):
    outcome_id: str
    signal_id: str
    session_id: str
    pair: str
    outcome_status: str
    executed_at: str | None = None
    entry_delta_summary: str | None = None
    exit_delta_summary: str | None = None
    pnl_value: float | None = None
    pnl_percent: float | None = None
    result_notes: list[str]
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/types/workspace.ts
export interface DemoReadinessSummary {
  sessionCount: number
  qualifiedSessionCount: number
  longSessionCount: number
  stableProfitFlag: boolean
  majorDrawdownFlag: boolean
  criticalTechnicalFailureFlag: boolean
  cautiousLiveReady: boolean
  blockingReasons: string[]
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/demo_trading/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test demo-contracts.test.ts --run
```

Expected: PASS with `E8` contracts available to backend and frontend.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/demo_trading frontend/src/types/workspace.ts backend/tests/demo_trading frontend/src/features/demo/demo-contracts.test.ts
git commit -m "feat: add e8 demo trading contracts"
```

### Task 2: Build Signal-To-Trade Linking And Reconciliation Logic

**Files:**
- Create: `backend/src/clay_mc/demo_trading/linking.py`
- Create: `backend/src/clay_mc/demo_trading/reconciliation.py`
- Create: `backend/tests/demo_trading/test_linking.py`
- Create: `backend/tests/demo_trading/test_reconciliation.py`

- [ ] **Step 1: Write the failing linking and reconciliation tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/demo_trading/test_linking.py
from clay_mc.demo_trading.linking import link_signal_to_demo_trade


def test_link_signal_to_demo_trade_marks_late_match_when_execution_is_delayed() -> None:
    result = link_signal_to_demo_trade(
        signal_id="sig-1",
        session_id="session-1",
        pair="BTCUSDT",
        expected_side="buy",
        signal_started_at="2026-04-15T10:00:00Z",
        signal_expires_at="2026-04-15T10:20:00Z",
        trade_pair="BTCUSDT",
        trade_side="buy",
        executed_at="2026-04-15T10:27:00Z",
    )

    assert result["link_status"] == "late_matched"
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/demo_trading/test_reconciliation.py
from clay_mc.demo_trading.reconciliation import deduplicate_demo_trades


def test_deduplicate_demo_trades_keeps_one_trade_per_source_identity() -> None:
    deduplicated = deduplicate_demo_trades(
        [
            {"demo_trade_id": "t-1", "external_id": "ex-1", "pair": "BTCUSDT"},
            {"demo_trade_id": "t-1-copy", "external_id": "ex-1", "pair": "BTCUSDT"},
        ]
    )

    assert len(deduplicated) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/demo_trading/test_linking.py tests/demo_trading/test_reconciliation.py -v
```

Expected: FAIL because linking and reconciliation helpers do not exist yet.

- [ ] **Step 3: Implement linking and reconciliation helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/demo_trading/linking.py
from datetime import datetime


def link_signal_to_demo_trade(
    signal_id: str,
    session_id: str,
    pair: str,
    expected_side: str,
    signal_started_at: str,
    signal_expires_at: str,
    trade_pair: str,
    trade_side: str,
    executed_at: str,
) -> dict[str, object]:
    if trade_pair != pair or trade_side != expected_side:
        return {"signal_id": signal_id, "session_id": session_id, "link_status": "mismatched"}

    executed = datetime.fromisoformat(executed_at.replace("Z", "+00:00"))
    expires = datetime.fromisoformat(signal_expires_at.replace("Z", "+00:00"))
    status = "matched" if executed <= expires else "late_matched"
    return {"signal_id": signal_id, "session_id": session_id, "link_status": status}
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/demo_trading/reconciliation.py
def deduplicate_demo_trades(trades: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for trade in trades:
        external_id = str(trade["external_id"])
        if external_id in seen:
            continue
        seen.add(external_id)
        result.append(trade)
    return result
```

- [ ] **Step 4: Run the tests and add `unresolved` coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/demo_trading/test_linking.py tests/demo_trading/test_reconciliation.py -v
```

Expected: PASS. Then add coverage for unresolved trades where timing, side, or source data are insufficient for safe linking.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/demo_trading backend/tests/demo_trading/test_linking.py backend/tests/demo_trading/test_reconciliation.py
git commit -m "feat: add e8 linking and reconciliation logic"
```

### Task 3: Build Demo Readiness Policy And Outcome Summaries

**Files:**
- Create: `backend/src/clay_mc/demo_trading/readiness.py`
- Create: `backend/tests/demo_trading/test_readiness.py`

- [ ] **Step 1: Write the failing readiness tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/demo_trading/test_readiness.py
from clay_mc.demo_trading.readiness import evaluate_demo_readiness


def test_evaluate_demo_readiness_blocks_live_when_critical_failure_exists() -> None:
    summary = evaluate_demo_readiness(
        session_count=5,
        qualified_session_count=5,
        long_session_count=2,
        stable_profit_flag=True,
        major_drawdown_flag=False,
        critical_technical_failure_flag=True,
    )

    assert summary["cautious_live_ready"] is False
    assert "critical_technical_failure" in summary["blocking_reasons"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/demo_trading/test_readiness.py -v
```

Expected: FAIL because readiness logic does not exist yet.

- [ ] **Step 3: Implement readiness evaluation**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/demo_trading/readiness.py
def evaluate_demo_readiness(
    session_count: int,
    qualified_session_count: int,
    long_session_count: int,
    stable_profit_flag: bool,
    major_drawdown_flag: bool,
    critical_technical_failure_flag: bool,
) -> dict[str, object]:
    blocking_reasons: list[str] = []
    if session_count < 5:
        blocking_reasons.append("insufficient_sessions")
    if long_session_count < 2:
        blocking_reasons.append("insufficient_long_sessions")
    if not stable_profit_flag:
        blocking_reasons.append("stable_profit_not_reached")
    if major_drawdown_flag:
        blocking_reasons.append("major_drawdown")
    if critical_technical_failure_flag:
        blocking_reasons.append("critical_technical_failure")

    return {
        "session_count": session_count,
        "qualified_session_count": qualified_session_count,
        "long_session_count": long_session_count,
        "stable_profit_flag": stable_profit_flag,
        "major_drawdown_flag": major_drawdown_flag,
        "critical_technical_failure_flag": critical_technical_failure_flag,
        "cautious_live_ready": len(blocking_reasons) == 0,
        "blocking_reasons": blocking_reasons,
    }
```

- [ ] **Step 4: Run the tests and add optimistic-false-positive coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/demo_trading/test_readiness.py -v
```

Expected: PASS. Then add coverage proving one lucky profitable session cannot set `cautious_live_ready=True`.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/demo_trading/readiness.py backend/tests/demo_trading/test_readiness.py
git commit -m "feat: add e8 demo readiness policy"
```

### Task 4: Build Demo Trading APIs Plus Streams

**Files:**
- Create: `backend/src/clay_mc/api/routes/demo_trades.py`
- Create: `backend/src/clay_mc/api/routes/demo_stage.py`
- Create: `backend/src/clay_mc/api/routes/demo_results_stream.py`
- Create: `backend/src/clay_mc/demo_trading/service.py`
- Create: `backend/src/clay_mc/demo_trading/streaming.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/api/test_demo_trades_api.py`
- Create: `backend/tests/api/test_demo_stage_api.py`
- Create: `backend/tests/api/test_demo_results_stream.py`

- [ ] **Step 1: Write the failing API and stream tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_demo_trades_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_recent_demo_trades_returns_observed_trade_items() -> None:
    client = TestClient(app)

    response = client.get("/demo-trades/recent")

    assert response.status_code == 200
    assert len(response.json()["items"]) > 0
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_demo_results_stream.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_demo_results_stream_returns_event_stream_response() -> None:
    client = TestClient(app)

    response = client.get("/demo-results/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_demo_trades_api.py tests/api/test_demo_stage_api.py tests/api/test_demo_results_stream.py -v
```

Expected: FAIL because the `E8` routes and streams do not exist yet.

- [ ] **Step 3: Implement routes and streaming**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/demo_trades.py
from fastapi import APIRouter


router = APIRouter(prefix="/demo-trades", tags=["demo-trades"])


@router.get("/recent")
def get_recent_demo_trades() -> dict[str, object]:
    return {
        "items": [
            {
                "demo_trade_id": "trade-1",
                "pair": "BTCUSDT",
                "side": "buy",
                "executed_at": "2026-04-15T12:00:00Z",
                "entry_price": 70250.0,
                "status": "filled",
                "source_label": "binance_demo",
            }
        ]
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/demo_results_stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/demo-results", tags=["demo-results-stream"])


def event_lines():
    yield "event: demo_outcome_updated\n"
    yield 'data: {"outcomeId":"outcome-1","outcomeStatus":"matched","resultLabel":"win"}\n\n'


@router.get("/stream")
def get_demo_results_stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream")
```

- [ ] **Step 4: Run the tests and add reconciliation coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_demo_trades_api.py tests/api/test_demo_stage_api.py tests/api/test_demo_results_stream.py -v
```

Expected: PASS. Then extend coverage for `POST /demo-results/reconcile`, `GET /signals/{signalId}/demo-link`, and `GET /demo-stage/readiness`.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api backend/src/clay_mc/demo_trading backend/tests/api/test_demo_trades_api.py backend/tests/api/test_demo_stage_api.py backend/tests/api/test_demo_results_stream.py
git commit -m "feat: add e8 demo result apis"
```

### Task 5: Wire Demo Result Visibility Into Trading Workspace

**Files:**
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/demo/components/demo-trade-card.tsx`
- Create: `frontend/src/features/demo/components/demo-outcome-card.tsx`
- Create: `frontend/src/features/demo/components/demo-link-status-chip.tsx`
- Create: `frontend/src/features/demo/components/demo-readiness-banner.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`

- [ ] **Step 1: Write the failing workspace rendering tests**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/trading-workspace-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TradingWorkspaceRoute } from './trading-workspace-route'

describe('TradingWorkspaceRoute E8 integrations', () => {
  it('renders demo trade, outcome, and readiness surfaces', () => {
    render(<TradingWorkspaceRoute />)

    expect(screen.getByText(/Demo Trade/i)).toBeInTheDocument()
    expect(screen.getByText(/Demo Outcome/i)).toBeInTheDocument()
    expect(screen.getByText(/Readiness/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: FAIL because the workspace has not been wired to `E8` result surfaces yet.

- [ ] **Step 3: Implement `E8`-aware demo components**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/demo/components/demo-link-status-chip.tsx
type Props = {
  linkStatus: 'matched' | 'missed' | 'late_matched' | 'mismatched' | 'unresolved'
}

export function DemoLinkStatusChip({ linkStatus }: Props) {
  return <span>Link status: {linkStatus}</span>
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/demo/components/demo-outcome-card.tsx
export function DemoOutcomeCard() {
  return (
    <section>
      <h2>Demo Outcome</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/demo/components/demo-readiness-banner.tsx
export function DemoReadinessBanner() {
  return (
    <section>
      <h2>Readiness</h2>
    </section>
  )
}
```

- [ ] **Step 4: Run the tests and add mismatch/unresolved coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: PASS. Then add UI coverage proving `late_matched`, `mismatched`, and `unresolved` outcomes render differently and do not look like clean trade confirmation.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/features/demo frontend/src/features/workspace frontend/src/api/workspace-client.ts frontend/src/stores/workspace-store.ts
git commit -m "feat: wire e8 demo result visibility into workspace"
```

### Task 6: Add End-To-End Coverage For Demo Validation Flow

**Files:**
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Write the failing end-to-end tests**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/tests/e2e/trading-workspace.spec.ts
import { expect, test } from '@playwright/test'

test('mismatched demo execution is visible as non-confirming outcome', async ({ page }) => {
  await page.goto('/trading')

  await expect(page.getByText(/Link status: mismatched/i)).toBeVisible()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: FAIL because end-to-end `E8` rendering is not complete yet.

- [ ] **Step 3: Implement the missing state hooks and docs updates**

```md
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/README.md
## E8 Demo Trading Validation

- `GET /demo-trades/recent` returns observed demo trade records
- `GET /demo-outcomes/recent` returns linked outcomes
- `GET /demo-stage/readiness` returns demo-stage readiness summary
- `GET /demo-results/stream` pushes live result updates

`E8` stays read-only for exchange-side execution. The operator still places demo trades manually.
```

- [ ] **Step 4: Run the tests and add readiness blocking coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: PASS. Then add end-to-end coverage for `missed` outcomes, stale reconciliation warnings, and readiness blocking caused by technical failures.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/tests/e2e/trading-workspace.spec.ts README.md
git commit -m "feat: finalize e8 demo validation coverage"
```

## Spec Coverage Check

- Demo trade, link, outcome, and readiness contracts are covered by Tasks 1 and 5.
- Signal-to-trade linking, `late_matched`, mismatch, deduplication, and reconciliation logic are covered by Task 2.
- Demo-stage readiness policy and blocking criteria are covered by Task 3.
- `HTTP + SSE` routes for recent trades, outcomes, readiness, and reconciliation are covered by Task 4.
- Workspace visibility for link status, trade outcome, and readiness surfaces is covered by Tasks 5 and 6.

## Assumptions

- `E6` and `E7` remain the canonical upstream sources for signal semantics and session discipline.
- Exchange integration in `E8` remains strictly read-only and never places demo orders.
- The route and file structure remain provisional until later demo-stage cleanup.

## Execution Handoff

Plan complete and saved to `implementation_plans/e8-demo-trading-integration-and-result-tracking-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
