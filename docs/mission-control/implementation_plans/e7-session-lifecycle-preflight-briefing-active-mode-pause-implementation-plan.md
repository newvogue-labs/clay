> **STATUS: HISTORICAL PLANNING (заморожен).** План относится к этапу планирования (апрель 2026) и сохраняется как исторический контекст.
> Источник истины — `blueprint-v1.md`, `release-gates.md`, ADR (`docs/adr/`) и код (`backend/`).
> Namespace в тексте — планировочный (`clay_mc`, `app/backend`); реальный код использует `clay` / `backend`.

# E7 Session Lifecycle: Preflight, Briefing, Active Mode, Pause Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working `E7` session lifecycle for `CLAY Mission Control`: hard `preflight`, structured `briefing`, guarded session admission, `active_session` transitions, `pause / resume` semantics, degraded recovery, and operator-confirmed pair replacement flow.

**Architecture:** The implementation extends the provisional `E1` repository with a dedicated `session_lifecycle` domain across backend and frontend. Backend services own `preflight` checks, `briefing` assembly, runtime transition guards, pair replacement proposals, and session event streaming. Frontend surfaces this backend truth in `Control Center` and `Trading Workspace` without inventing wizard-state locally. `E7` stays downstream of `E3` workspace contracts, `E4` operational control, and `E6` signal/risk semantics, and upstream of `E8` demo execution tracking.

**Tech Stack:** React 19, TypeScript 5.x, Vite, React Router, Zustand, TanStack Query, FastAPI, Pydantic v2, pytest, Vitest, Testing Library, Playwright, Server-Sent Events

---

## Repository Root

This plan assumes the working application repository will live at:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app`

Important:

- this remains a `provisional implementation layout`;
- a later structural refactor is still allowed after demo validation;
- until then, keep session discipline in backend guards and contracts, not in frontend optimism, stale tabs, or ritual sacrifices to the event loop.

## File Structure

### Backend

- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/preflight.py`
- Create: `backend/src/clay_mc/api/routes/briefing.py`
- Create: `backend/src/clay_mc/api/routes/session.py`
- Create: `backend/src/clay_mc/api/routes/session_stream.py`
- Create: `backend/src/clay_mc/session_lifecycle/models.py`
- Create: `backend/src/clay_mc/session_lifecycle/preflight.py`
- Create: `backend/src/clay_mc/session_lifecycle/briefing.py`
- Create: `backend/src/clay_mc/session_lifecycle/runtime_transitions.py`
- Create: `backend/src/clay_mc/session_lifecycle/pair_replacement.py`
- Create: `backend/src/clay_mc/session_lifecycle/service.py`
- Create: `backend/src/clay_mc/session_lifecycle/streaming.py`
- Create: `backend/tests/api/test_preflight_api.py`
- Create: `backend/tests/api/test_session_api.py`
- Create: `backend/tests/api/test_session_stream.py`
- Create: `backend/tests/session_lifecycle/test_models.py`
- Create: `backend/tests/session_lifecycle/test_preflight.py`
- Create: `backend/tests/session_lifecycle/test_runtime_transitions.py`
- Create: `backend/tests/session_lifecycle/test_pair_replacement.py`

### Frontend

- Modify: `frontend/src/types/workspace.ts`
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/session/components/preflight-status-panel.tsx`
- Create: `frontend/src/features/session/components/briefing-summary-card.tsx`
- Create: `frontend/src/features/session/components/session-state-banner.tsx`
- Create: `frontend/src/features/session/components/pair-replacement-card.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`
- Create: `frontend/src/features/session/session-contracts.test.ts`
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`

### Repo-level

- Modify: `README.md`

---

### Task 1: Establish Preflight, Briefing, And Session Contracts

**Files:**
- Create: `backend/src/clay_mc/session_lifecycle/models.py`
- Modify: `frontend/src/types/workspace.ts`
- Create: `backend/tests/session_lifecycle/test_models.py`
- Create: `frontend/src/features/session/session-contracts.test.ts`

- [ ] **Step 1: Write the failing contract tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/session_lifecycle/test_models.py
from clay_mc.session_lifecycle.models import PreflightResultRecord


def test_preflight_result_record_contains_status_checks_and_admission_flag() -> None:
    record = PreflightResultRecord.model_validate(
        {
            "preflight_id": "pf-1",
            "status": "soft_fail",
            "started_at": "2026-04-15T10:00:00Z",
            "finished_at": "2026-04-15T10:00:12Z",
            "checks": [{"check_id": "market-freshness", "status": "warning"}],
            "blocking_reasons": [],
            "soft_warnings": ["sentiment connector degraded"],
            "can_enter_active_session": True,
        }
    )

    assert record.status == "soft_fail"
    assert record.can_enter_active_session is True
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/session/session-contracts.test.ts
import { describe, expect, it } from 'vitest'
import type { SessionStateSnapshot } from '../../types/workspace'

describe('session lifecycle contracts', () => {
  it('defines the minimum runtime session state shape', () => {
    const snapshot: SessionStateSnapshot = {
      runtimeState: 'pre_session',
      sessionId: null,
      sessionStartedAt: null,
      pauseReason: null,
      degradedReason: null,
      canResume: false,
      canEnterActiveSession: false,
    }

    expect(snapshot.runtimeState).toBe('pre_session')
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/session_lifecycle/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test session-contracts.test.ts --run
```

Expected: FAIL because `E7` contracts do not exist yet.

- [ ] **Step 3: Implement shared session lifecycle contracts**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/session_lifecycle/models.py
from pydantic import BaseModel


class PreflightCheckRecord(BaseModel):
    check_id: str
    status: str
    summary: str | None = None


class PreflightResultRecord(BaseModel):
    preflight_id: str
    status: str
    started_at: str
    finished_at: str | None = None
    checks: list[PreflightCheckRecord]
    blocking_reasons: list[str]
    soft_warnings: list[str]
    can_enter_active_session: bool
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/types/workspace.ts
export interface SessionStateSnapshot {
  runtimeState: 'background_monitoring' | 'pre_session' | 'active_session' | 'paused' | 'review' | 'degraded'
  sessionId: string | null
  sessionStartedAt: string | null
  pauseReason: string | null
  degradedReason: string | null
  canResume: boolean
  canEnterActiveSession: boolean
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/session_lifecycle/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test session-contracts.test.ts --run
```

Expected: PASS with `E7` contracts available to backend and frontend.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/session_lifecycle frontend/src/types/workspace.ts backend/tests/session_lifecycle frontend/src/features/session/session-contracts.test.ts
git commit -m "feat: add e7 session lifecycle contracts"
```

### Task 2: Build Hard Preflight And Briefing Assembly Logic

**Files:**
- Create: `backend/src/clay_mc/session_lifecycle/preflight.py`
- Create: `backend/src/clay_mc/session_lifecycle/briefing.py`
- Create: `backend/tests/session_lifecycle/test_preflight.py`

- [ ] **Step 1: Write the failing preflight tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/session_lifecycle/test_preflight.py
from clay_mc.session_lifecycle.preflight import run_preflight


def test_run_preflight_blocks_active_session_on_hard_failure() -> None:
    result = run_preflight(
        runtime_ready=True,
        services_ready=True,
        market_data_fresh=False,
        config_valid=True,
        model_assignment_valid=True,
        risk_limits_loaded=True,
    )

    assert result["status"] == "hard_fail"
    assert result["can_enter_active_session"] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/session_lifecycle/test_preflight.py -v
```

Expected: FAIL because preflight logic does not exist yet.

- [ ] **Step 3: Implement preflight and briefing helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/session_lifecycle/preflight.py
def run_preflight(
    runtime_ready: bool,
    services_ready: bool,
    market_data_fresh: bool,
    config_valid: bool,
    model_assignment_valid: bool,
    risk_limits_loaded: bool,
) -> dict[str, object]:
    checks = {
        "runtime": runtime_ready,
        "services": services_ready,
        "market_data": market_data_fresh,
        "config": config_valid,
        "model_assignment": model_assignment_valid,
        "risk_limits": risk_limits_loaded,
    }
    failed = [name for name, ok in checks.items() if not ok]
    status = "pass" if not failed else "hard_fail"
    return {
        "status": status,
        "checks": checks,
        "blocking_reasons": failed,
        "soft_warnings": [],
        "can_enter_active_session": status == "pass",
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/session_lifecycle/briefing.py
def build_briefing(primary_focus_pair: str, backup_pairs: list[str], active_strategy: str) -> dict[str, object]:
    return {
        "briefing_id": "brief-1",
        "primary_focus_pair": primary_focus_pair,
        "backup_pairs": backup_pairs,
        "active_strategy": active_strategy,
        "risk_alerts": [],
        "ai_summary": "Session summary ready",
        "market_context_summary": "Baseline market context available",
        "sentiment_summary": "Sentiment feed available",
    }
```

- [ ] **Step 4: Run the tests and add `soft_fail` coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/session_lifecycle/test_preflight.py -v
```

Expected: PASS. Then extend coverage for `soft_fail`, where non-critical degraded inputs still require explicit operator awareness before session admission.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/session_lifecycle backend/tests/session_lifecycle/test_preflight.py
git commit -m "feat: add e7 preflight and briefing assembly"
```

### Task 3: Build Runtime Transition Guards And Pair Replacement Logic

**Files:**
- Create: `backend/src/clay_mc/session_lifecycle/runtime_transitions.py`
- Create: `backend/src/clay_mc/session_lifecycle/pair_replacement.py`
- Create: `backend/tests/session_lifecycle/test_runtime_transitions.py`
- Create: `backend/tests/session_lifecycle/test_pair_replacement.py`

- [ ] **Step 1: Write the failing transition and proposal tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/session_lifecycle/test_runtime_transitions.py
from clay_mc.session_lifecycle.runtime_transitions import can_transition


def test_degraded_cannot_jump_directly_to_active_session() -> None:
    allowed, reason = can_transition(
        current_state="degraded",
        target_state="active_session",
        preflight_status="pass",
        degraded_blocking=False,
    )

    assert allowed is False
    assert reason == "revalidation_required"
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/session_lifecycle/test_pair_replacement.py
from clay_mc.session_lifecycle.pair_replacement import build_pair_replacement_proposal


def test_pair_replacement_requires_confirmation_and_reason_summary() -> None:
    proposal = build_pair_replacement_proposal(
        current_pair="BTCUSDT",
        proposed_pair="ETHUSDT",
        reason_summary="Higher ranked and lower risk candidate",
    )

    assert proposal["requires_confirmation"] is True
    assert proposal["current_pair"] == "BTCUSDT"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/session_lifecycle/test_runtime_transitions.py tests/session_lifecycle/test_pair_replacement.py -v
```

Expected: FAIL because transition guards and pair replacement helpers do not exist yet.

- [ ] **Step 3: Implement transition guards and replacement helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/session_lifecycle/runtime_transitions.py
def can_transition(
    current_state: str,
    target_state: str,
    preflight_status: str,
    degraded_blocking: bool,
) -> tuple[bool, str | None]:
    if current_state == "degraded" and target_state == "active_session":
        return False, "revalidation_required"
    if target_state == "active_session" and preflight_status == "hard_fail":
        return False, "preflight_blocked"
    if target_state == "active_session" and degraded_blocking:
        return False, "degraded_blocking_condition"
    return True, None
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/session_lifecycle/pair_replacement.py
def build_pair_replacement_proposal(
    current_pair: str,
    proposed_pair: str,
    reason_summary: str,
) -> dict[str, object]:
    return {
        "proposal_id": "pair-proposal-1",
        "current_pair": current_pair,
        "proposed_pair": proposed_pair,
        "reason_summary": reason_summary,
        "confidence_diff": 0.11,
        "risk_diff": -0.09,
        "requires_confirmation": True,
    }
```

- [ ] **Step 4: Run the tests and add pause/resume coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/session_lifecycle/test_runtime_transitions.py tests/session_lifecycle/test_pair_replacement.py -v
```

Expected: PASS. Then add coverage for `paused -> active_session` success only when blocking degraded conditions are absent and lightweight revalidation rules are satisfied.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/session_lifecycle backend/tests/session_lifecycle/test_runtime_transitions.py backend/tests/session_lifecycle/test_pair_replacement.py
git commit -m "feat: add e7 transition guards and pair replacement flow"
```

### Task 4: Build Preflight, Briefing, And Session APIs Plus Streams

**Files:**
- Create: `backend/src/clay_mc/api/routes/preflight.py`
- Create: `backend/src/clay_mc/api/routes/briefing.py`
- Create: `backend/src/clay_mc/api/routes/session.py`
- Create: `backend/src/clay_mc/api/routes/session_stream.py`
- Create: `backend/src/clay_mc/session_lifecycle/service.py`
- Create: `backend/src/clay_mc/session_lifecycle/streaming.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/api/test_preflight_api.py`
- Create: `backend/tests/api/test_session_api.py`
- Create: `backend/tests/api/test_session_stream.py`

- [ ] **Step 1: Write the failing API and stream tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_preflight_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_preflight_latest_returns_admission_payload() -> None:
    client = TestClient(app)

    response = client.get("/preflight/latest")

    assert response.status_code == 200
    assert "can_enter_active_session" in response.json()
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_session_stream.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_session_events_stream_returns_event_stream_response() -> None:
    client = TestClient(app)

    response = client.get("/session/events/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_preflight_api.py tests/api/test_session_api.py tests/api/test_session_stream.py -v
```

Expected: FAIL because the `E7` routes and session stream do not exist yet.

- [ ] **Step 3: Implement routes and streaming**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/preflight.py
from fastapi import APIRouter


router = APIRouter(prefix="/preflight", tags=["preflight"])


@router.get("/latest")
def get_latest_preflight() -> dict[str, object]:
    return {
        "preflight_id": "pf-1",
        "status": "pass",
        "checks": [],
        "blocking_reasons": [],
        "soft_warnings": [],
        "can_enter_active_session": True,
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/session_stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/session", tags=["session-stream"])


def event_lines():
    yield "event: session_state_changed\n"
    yield 'data: {"runtimeState":"paused","pauseReason":"operator_pause"}\n\n'


@router.get("/events/stream")
def get_session_events_stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream")
```

- [ ] **Step 4: Run the tests and add command coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_preflight_api.py tests/api/test_session_api.py tests/api/test_session_stream.py -v
```

Expected: PASS. Then extend coverage for `POST /preflight/run`, `GET /briefing/current`, `POST /session/start`, `POST /session/pause`, `POST /session/resume`, and pair replacement accept/reject commands.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api backend/src/clay_mc/session_lifecycle backend/tests/api/test_preflight_api.py backend/tests/api/test_session_api.py backend/tests/api/test_session_stream.py
git commit -m "feat: add e7 preflight and session apis"
```

### Task 5: Wire Session Lifecycle Contracts Into Control Center And Trading Workspace

**Files:**
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/session/components/preflight-status-panel.tsx`
- Create: `frontend/src/features/session/components/briefing-summary-card.tsx`
- Create: `frontend/src/features/session/components/session-state-banner.tsx`
- Create: `frontend/src/features/session/components/pair-replacement-card.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`

- [ ] **Step 1: Write the failing workspace rendering tests**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/trading-workspace-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TradingWorkspaceRoute } from './trading-workspace-route'

describe('TradingWorkspaceRoute E7 integrations', () => {
  it('renders preflight, briefing, and session state surfaces', () => {
    render(<TradingWorkspaceRoute />)

    expect(screen.getByText(/Preflight/i)).toBeInTheDocument()
    expect(screen.getByText(/Session Briefing/i)).toBeInTheDocument()
    expect(screen.getByText(/Session State/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: FAIL because the workspace has not been wired to `E7` session lifecycle surfaces yet.

- [ ] **Step 3: Implement `E7`-aware session components**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/session/components/session-state-banner.tsx
type Props = {
  runtimeState: 'background_monitoring' | 'pre_session' | 'active_session' | 'paused' | 'review' | 'degraded'
}

export function SessionStateBanner({ runtimeState }: Props) {
  return <section>Session State: {runtimeState}</section>
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/session/components/preflight-status-panel.tsx
export function PreflightStatusPanel() {
  return (
    <section>
      <h2>Preflight</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/session/components/briefing-summary-card.tsx
export function BriefingSummaryCard() {
  return (
    <section>
      <h2>Session Briefing</h2>
    </section>
  )
}
```

- [ ] **Step 4: Run the tests and add degraded/pause coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: PASS. Then add UI coverage proving `soft_fail`, `paused`, and `degraded` states render differently and never look like fully green normal mode.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/features/session frontend/src/features/workspace frontend/src/api/workspace-client.ts frontend/src/stores/workspace-store.ts
git commit -m "feat: wire e7 session lifecycle into workspace"
```

### Task 6: Add End-To-End Coverage For Session Admission, Pause, And Recovery

**Files:**
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Write the failing end-to-end tests**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/tests/e2e/trading-workspace.spec.ts
import { expect, test } from '@playwright/test'

test('hard preflight failure blocks active session entry', async ({ page }) => {
  await page.goto('/trading')

  await expect(page.getByText(/cannot enter active session/i)).toBeVisible()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: FAIL because end-to-end `E7` flow handling is not complete yet.

- [ ] **Step 3: Implement the missing state hooks and docs updates**

```md
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/README.md
## E7 Session Lifecycle

- `GET /preflight/latest` returns the latest admission snapshot
- `GET /briefing/current` returns the current pre-session briefing
- `GET /session/state` returns canonical session state
- `GET /session/events/stream` pushes session state changes

No client is allowed to enter `active_session` by inventing local success state.
```

- [ ] **Step 4: Run the tests and add resume edge-case coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: PASS. Then add end-to-end coverage for `soft_fail` with conditional continuation, long-pause revalidation, and degraded recovery requiring a new `preflight`.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/tests/e2e/trading-workspace.spec.ts README.md
git commit -m "feat: finalize e7 session lifecycle coverage"
```

## Spec Coverage Check

- `Preflight` contracts, admission semantics, and session-facing snapshots are covered by Tasks 1 and 4.
- Hard `preflight`, `soft_fail`, and `briefing` assembly are covered by Task 2.
- Runtime transition discipline, pause/resume guards, degraded recovery rules, and pair replacement proposals are covered by Task 3.
- `HTTP + SSE` routes for `preflight`, `briefing`, and session events are covered by Task 4.
- Workspace visibility for `preflight`, `briefing`, `paused`, `degraded`, and pair replacement flows is covered by Tasks 5 and 6.

## Assumptions

- `E3`, `E4`, and `E6` remain the canonical upstream sources for workspace, runtime, and risk semantics.
- `Briefing` remains a required handoff artifact and cannot be silently skipped by frontend routing.
- The route and file structure remain provisional until later demo-stage cleanup.

## Execution Handoff

Plan complete and saved to `implementation_plans/e7-session-lifecycle-preflight-briefing-active-mode-pause-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
