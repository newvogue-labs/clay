> **STATUS: HISTORICAL PLANNING (заморожен).** План относится к этапу планирования (апрель 2026) и сохраняется как исторический контекст.
> Источник истины — `blueprint-v1.md`, `release-gates.md`, ADR (`docs/adr/`) и код (`backend/`).
> Namespace в тексте — планировочный (`clay_mc`, `app/backend`); реальный код использует `clay` / `backend`.

# E12 Reliability, Degraded Mode And Release Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working `E12` reliability layer for `CLAY Mission Control`: degraded-mode state handling, local fallback visibility, readiness checks, release gates, and operator-facing incident evidence across runtime, review, and demo validation.

**Architecture:** The implementation extends the provisional `E1` repository with a `reliability` domain across backend and frontend. Backend services own canonical degraded snapshots, incident records, fallback capability policy, readiness evaluation, and release gate decisions. Frontend surfaces reliability truth from backend snapshots and streams without inventing local “everything is fine” toggles or masking degraded behavior behind optimistic UI states. `E12` sits downstream of `E7`, `E8`, `E9`, and `E11`, and closes the `v1` planning chain before real implementation begins.

**Tech Stack:** React 19, TypeScript 5.x, Vite, React Router, Zustand, TanStack Query, FastAPI, Pydantic v2, pytest, Vitest, Testing Library, Playwright, Server-Sent Events

---

## Repository Root

This plan assumes the working application repository will live at:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app`

Important:

- this remains a `provisional implementation layout`;
- a later structural refactor is still allowed after demo validation;
- until then, keep reliability truth in backend incident state, readiness checks, and gate evaluation, not in browser-local flags, heroic guesswork, or “works on my laptop” theology.

## File Structure

### Backend

- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/reliability.py`
- Create: `backend/src/clay_mc/api/routes/reliability_stream.py`
- Create: `backend/src/clay_mc/api/routes/readiness.py`
- Create: `backend/src/clay_mc/api/routes/release_gates.py`
- Create: `backend/src/clay_mc/reliability/models.py`
- Create: `backend/src/clay_mc/reliability/incidents.py`
- Create: `backend/src/clay_mc/reliability/fallback.py`
- Create: `backend/src/clay_mc/reliability/readiness.py`
- Create: `backend/src/clay_mc/reliability/release_gates.py`
- Create: `backend/src/clay_mc/reliability/service.py`
- Create: `backend/src/clay_mc/reliability/streaming.py`
- Create: `backend/tests/api/test_reliability_api.py`
- Create: `backend/tests/api/test_reliability_stream.py`
- Create: `backend/tests/api/test_readiness_api.py`
- Create: `backend/tests/api/test_release_gates_api.py`
- Create: `backend/tests/reliability/test_models.py`
- Create: `backend/tests/reliability/test_incidents.py`
- Create: `backend/tests/reliability/test_fallback.py`
- Create: `backend/tests/reliability/test_readiness.py`
- Create: `backend/tests/reliability/test_release_gates.py`

### Frontend

- Modify: `frontend/src/types/workspace.ts`
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`
- Create: `frontend/src/features/reliability/components/degraded-status-banner.tsx`
- Create: `frontend/src/features/reliability/components/incident-timeline-card.tsx`
- Create: `frontend/src/features/reliability/components/fallback-capability-card.tsx`
- Create: `frontend/src/features/reliability/components/readiness-checklist-card.tsx`
- Create: `frontend/src/features/reliability/components/release-gates-card.tsx`
- Create: `frontend/src/features/reliability/reliability-contracts.test.ts`
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`

### Repo-level

- Modify: `README.md`

---

### Task 1: Establish Reliability, Readiness, And Release Gate Contracts

**Files:**
- Create: `backend/src/clay_mc/reliability/models.py`
- Create: `backend/tests/reliability/test_models.py`
- Modify: `frontend/src/types/workspace.ts`
- Create: `frontend/src/features/reliability/reliability-contracts.test.ts`

- [ ] **Step 1: Write the failing contract tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/reliability/test_models.py
from clay_mc.reliability.models import DegradedStateSnapshotRecord


def test_degraded_state_snapshot_contains_reason_codes_and_confidence_policy() -> None:
    snapshot = DegradedStateSnapshotRecord.model_validate(
        {
            "snapshot_id": "snapshot-1",
            "mode": "degraded",
            "entered_at": "2026-04-15T12:00:00Z",
            "reason_codes": ["provider_outage"],
            "blocked_features": ["session_start"],
            "limited_features": ["signal_ranking"],
            "confidence_policy": "reduced_confidence",
            "operator_message": "Cloud provider unavailable. Fallback mode active.",
        }
    )

    assert snapshot.mode == "degraded"
    assert snapshot.confidence_policy == "reduced_confidence"
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/reliability/reliability-contracts.test.ts
import { describe, expect, it } from 'vitest'
import type { ReleaseGateDecision } from '../../types/workspace'

describe('reliability contracts', () => {
  it('defines a minimum release gate decision shape', () => {
    const gate: ReleaseGateDecision = {
      gateId: 'gate-1',
      releaseStage: 'demo_readiness',
      gateName: 'degraded_visibility_gate',
      status: 'blocked',
      requiredChecks: ['readiness.degraded_visibility'],
      reviewSummary: 'Fallback state is not visible in workspace yet.',
      approvedBy: null,
      approvedAt: null,
    }

    expect(gate.status).toBe('blocked')
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/reliability/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test reliability-contracts.test.ts --run
```

Expected: FAIL because the `E12` reliability contracts do not exist yet.

- [ ] **Step 3: Implement shared reliability contracts**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/reliability/models.py
from pydantic import BaseModel


class DegradedStateSnapshotRecord(BaseModel):
    snapshot_id: str
    mode: str
    entered_at: str | None
    reason_codes: list[str]
    blocked_features: list[str]
    limited_features: list[str]
    confidence_policy: str
    operator_message: str
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/types/workspace.ts
export interface ReleaseGateDecision {
  gateId: string
  releaseStage: string
  gateName: string
  status: 'ready' | 'blocked' | 'review_required'
  requiredChecks: string[]
  reviewSummary: string
  approvedBy: string | null
  approvedAt: string | null
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/reliability/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test reliability-contracts.test.ts --run
```

Expected: PASS with `E12` contracts available to backend and frontend.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/reliability backend/tests/reliability/test_models.py frontend/src/types/workspace.ts frontend/src/features/reliability/reliability-contracts.test.ts
git commit -m "feat: add e12 reliability contracts"
```

### Task 2: Build Incident And Fallback Policy Logic

**Files:**
- Create: `backend/src/clay_mc/reliability/incidents.py`
- Create: `backend/src/clay_mc/reliability/fallback.py`
- Create: `backend/tests/reliability/test_incidents.py`
- Create: `backend/tests/reliability/test_fallback.py`

- [ ] **Step 1: Write the failing incident and fallback tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/reliability/test_incidents.py
from clay_mc.reliability.incidents import build_degraded_snapshot


def test_build_degraded_snapshot_marks_session_start_as_blocked() -> None:
    snapshot = build_degraded_snapshot(
        reason_codes=["provider_outage"],
        blocked_features=["session_start"],
        limited_features=["signal_ranking"],
    )

    assert snapshot["mode"] == "degraded"
    assert "session_start" in snapshot["blocked_features"]
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/reliability/test_fallback.py
from clay_mc.reliability.fallback import build_fallback_capability_record


def test_build_fallback_capability_record_preserves_limitations() -> None:
    capability = build_fallback_capability_record(
        fallback_type="local_text_assist",
        available_actions=["review_triage"],
        blocked_actions=["strategy_activation"],
        quality_limitations=["No chief-agent synthesis"],
    )

    assert capability["fallback_type"] == "local_text_assist"
    assert capability["blocked_actions"] == ["strategy_activation"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/reliability/test_incidents.py tests/reliability/test_fallback.py -v
```

Expected: FAIL because incident and fallback helpers do not exist yet.

- [ ] **Step 3: Implement incident and fallback helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/reliability/incidents.py
def build_degraded_snapshot(
    reason_codes: list[str],
    blocked_features: list[str],
    limited_features: list[str],
) -> dict[str, object]:
    return {
        "snapshot_id": "snapshot-1",
        "mode": "degraded",
        "entered_at": "2026-04-15T12:00:00Z",
        "reason_codes": reason_codes,
        "blocked_features": blocked_features,
        "limited_features": limited_features,
        "confidence_policy": "reduced_confidence",
        "operator_message": "Critical upstream dependency unavailable.",
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/reliability/fallback.py
def build_fallback_capability_record(
    fallback_type: str,
    available_actions: list[str],
    blocked_actions: list[str],
    quality_limitations: list[str],
) -> dict[str, object]:
    return {
        "capability_id": "cap-1",
        "fallback_type": fallback_type,
        "available_actions": available_actions,
        "blocked_actions": blocked_actions,
        "quality_limitations": quality_limitations,
        "activation_rule": "primary_provider_unavailable",
        "recovery_rule": "restore_full_mode_after_successful_health_check",
    }
```

- [ ] **Step 4: Run the tests and add non-silent degraded coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/reliability/test_incidents.py tests/reliability/test_fallback.py -v
```

Expected: PASS. Then add coverage proving degraded snapshots always include operator-facing message and fallback limitations instead of silent downgrade behavior.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/reliability/incidents.py backend/src/clay_mc/reliability/fallback.py backend/tests/reliability/test_incidents.py backend/tests/reliability/test_fallback.py
git commit -m "feat: add e12 degraded and fallback logic"
```

### Task 3: Build Readiness Checks And Release Gate Evaluation

**Files:**
- Create: `backend/src/clay_mc/reliability/readiness.py`
- Create: `backend/src/clay_mc/reliability/release_gates.py`
- Create: `backend/tests/reliability/test_readiness.py`
- Create: `backend/tests/reliability/test_release_gates.py`

- [ ] **Step 1: Write the failing readiness and release gate tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/reliability/test_readiness.py
from clay_mc.reliability.readiness import evaluate_demo_readiness


def test_evaluate_demo_readiness_blocks_when_audit_or_demo_results_are_missing() -> None:
    readiness = evaluate_demo_readiness(
        has_preflight=True,
        has_risk_controls=True,
        has_audit_trail=False,
        has_demo_results=False,
        has_degraded_visibility=True,
    )

    assert readiness["status"] == "blocked"
    assert len(readiness["failed_checks"]) == 2
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/reliability/test_release_gates.py
from clay_mc.reliability.release_gates import build_release_gate_decision


def test_build_release_gate_decision_requires_failed_checks_for_blocked_state() -> None:
    gate = build_release_gate_decision(
        release_stage="demo_readiness",
        gate_name="audit_trail_gate",
        failed_checks=["audit.events_visible"],
    )

    assert gate["status"] == "blocked"
    assert gate["required_checks"] == ["audit.events_visible"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/reliability/test_readiness.py tests/reliability/test_release_gates.py -v
```

Expected: FAIL because readiness and release gate helpers do not exist yet.

- [ ] **Step 3: Implement readiness and release gate helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/reliability/readiness.py
def evaluate_demo_readiness(
    has_preflight: bool,
    has_risk_controls: bool,
    has_audit_trail: bool,
    has_demo_results: bool,
    has_degraded_visibility: bool,
) -> dict[str, object]:
    failed_checks: list[str] = []

    if not has_preflight:
        failed_checks.append("preflight.ready")
    if not has_risk_controls:
        failed_checks.append("risk_controls.ready")
    if not has_audit_trail:
        failed_checks.append("audit.ready")
    if not has_demo_results:
        failed_checks.append("demo_results.ready")
    if not has_degraded_visibility:
        failed_checks.append("degraded_visibility.ready")

    return {
        "status": "ready" if not failed_checks else "blocked",
        "failed_checks": failed_checks,
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/reliability/release_gates.py
def build_release_gate_decision(
    release_stage: str,
    gate_name: str,
    failed_checks: list[str],
) -> dict[str, object]:
    return {
        "gate_id": f"{release_stage}:{gate_name}",
        "release_stage": release_stage,
        "gate_name": gate_name,
        "status": "ready" if not failed_checks else "blocked",
        "required_checks": failed_checks,
        "review_summary": "All required checks passed." if not failed_checks else "Critical readiness evidence is missing.",
        "approved_by": None,
        "approved_at": None,
    }
```

- [ ] **Step 4: Run the tests and add review-required coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/reliability/test_readiness.py tests/reliability/test_release_gates.py -v
```

Expected: PASS. Then add coverage for `review_required` gate state when checks technically pass but operator approval is still pending.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/reliability/readiness.py backend/src/clay_mc/reliability/release_gates.py backend/tests/reliability/test_readiness.py backend/tests/reliability/test_release_gates.py
git commit -m "feat: add e12 readiness and release gate logic"
```

### Task 4: Build Reliability APIs Plus Incident Stream

**Files:**
- Create: `backend/src/clay_mc/api/routes/reliability.py`
- Create: `backend/src/clay_mc/api/routes/reliability_stream.py`
- Create: `backend/src/clay_mc/api/routes/readiness.py`
- Create: `backend/src/clay_mc/api/routes/release_gates.py`
- Create: `backend/src/clay_mc/reliability/service.py`
- Create: `backend/src/clay_mc/reliability/streaming.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/api/test_reliability_api.py`
- Create: `backend/tests/api/test_reliability_stream.py`
- Create: `backend/tests/api/test_readiness_api.py`
- Create: `backend/tests/api/test_release_gates_api.py`

- [ ] **Step 1: Write the failing API and stream tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_reliability_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_reliability_snapshot_endpoint_returns_degraded_payload() -> None:
    client = TestClient(app)

    response = client.get("/reliability/snapshot")

    assert response.status_code == 200
    assert "mode" in response.json()
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_reliability_stream.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_reliability_stream_returns_event_stream_response() -> None:
    client = TestClient(app)

    response = client.get("/reliability/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_reliability_api.py tests/api/test_reliability_stream.py tests/api/test_readiness_api.py tests/api/test_release_gates_api.py -v
```

Expected: FAIL because the `E12` routes and reliability stream do not exist yet.

- [ ] **Step 3: Implement routes and streaming**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/reliability.py
from fastapi import APIRouter


router = APIRouter(prefix="/reliability", tags=["reliability"])


@router.get("/snapshot")
def get_reliability_snapshot() -> dict[str, object]:
    return {
        "snapshot_id": "snapshot-1",
        "mode": "degraded",
        "reason_codes": ["provider_outage"],
        "blocked_features": ["session_start"],
        "limited_features": ["signal_ranking"],
        "confidence_policy": "reduced_confidence",
        "operator_message": "Cloud provider unavailable. Fallback active.",
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/reliability_stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/reliability", tags=["reliability-stream"])


def event_lines():
    yield "event: reliability_incident\n"
    yield 'data: {"mode":"degraded","reasonCodes":["provider_outage"],"fallbackActive":true}\n\n'


@router.get("/stream")
def get_reliability_stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream")
```

- [ ] **Step 4: Run the tests and add readiness endpoint coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_reliability_api.py tests/api/test_reliability_stream.py tests/api/test_readiness_api.py tests/api/test_release_gates_api.py -v
```

Expected: PASS. Then extend coverage for `GET /reliability/incidents`, `GET /readiness/checks`, `GET /release-gates`, and explicit degraded-recovery events.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api backend/src/clay_mc/reliability backend/tests/api/test_reliability_api.py backend/tests/api/test_reliability_stream.py backend/tests/api/test_readiness_api.py backend/tests/api/test_release_gates_api.py
git commit -m "feat: add e12 reliability apis"
```

### Task 5: Wire Reliability Surfaces Into Workspace UI

**Files:**
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`
- Create: `frontend/src/features/reliability/components/degraded-status-banner.tsx`
- Create: `frontend/src/features/reliability/components/incident-timeline-card.tsx`
- Create: `frontend/src/features/reliability/components/fallback-capability-card.tsx`
- Create: `frontend/src/features/reliability/components/readiness-checklist-card.tsx`
- Create: `frontend/src/features/reliability/components/release-gates-card.tsx`

- [ ] **Step 1: Write the failing workspace rendering tests**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/trading-workspace-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TradingWorkspaceRoute } from './trading-workspace-route'

describe('TradingWorkspaceRoute E12 integrations', () => {
  it('renders degraded status, readiness, and release gates', () => {
    render(<TradingWorkspaceRoute />)

    expect(screen.getByText(/Degraded Mode/i)).toBeInTheDocument()
    expect(screen.getByText(/Readiness Checklist/i)).toBeInTheDocument()
    expect(screen.getByText(/Release Gates/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: FAIL because the workspace has not been wired to `E12` reliability surfaces yet.

- [ ] **Step 3: Implement `E12`-aware reliability components**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/reliability/components/degraded-status-banner.tsx
export function DegradedStatusBanner() {
  return (
    <section>
      <h2>Degraded Mode</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/reliability/components/readiness-checklist-card.tsx
export function ReadinessChecklistCard() {
  return (
    <section>
      <h2>Readiness Checklist</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/reliability/components/release-gates-card.tsx
export function ReleaseGatesCard() {
  return (
    <section>
      <h2>Release Gates</h2>
    </section>
  )
}
```

- [ ] **Step 4: Run the tests and add degraded recovery coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: PASS. Then add UI coverage proving blocked features, fallback limitations, and gate failures remain visible and cannot be confused with healthy full-mode state.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/features/reliability frontend/src/features/workspace frontend/src/api/workspace-client.ts frontend/src/stores/workspace-store.ts
git commit -m "feat: wire e12 reliability into workspace"
```

### Task 6: Add End-To-End Coverage For Degraded Mode And Readiness Gates

**Files:**
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Write the failing end-to-end tests**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/tests/e2e/trading-workspace.spec.ts
import { expect, test } from '@playwright/test'

test('degraded mode and blocked release gates are visible in workspace', async ({ page }) => {
  await page.goto('/trading')

  await expect(page.getByText(/Degraded Mode/i)).toBeVisible()
  await expect(page.getByText(/Release Gates/i)).toBeVisible()
  await expect(page.getByText(/blocked/i)).toBeVisible()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: FAIL because end-to-end `E12` rendering is not complete yet.

- [ ] **Step 3: Implement the missing state hooks and docs updates**

```md
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/README.md
## E12 Reliability And Release Readiness

- `GET /reliability/snapshot` returns current full-mode or degraded snapshot
- `GET /reliability/stream` pushes degraded incidents and recovery events
- `GET /readiness/checks` returns readiness evidence and failures
- `GET /release-gates` returns milestone gate decisions

Reliability visibility is mandatory. Fallback never pretends to be full mode, and blocked release gates must remain visible until evidence improves or the operator explicitly reviews them.
```

- [ ] **Step 4: Run the tests and add incident-history coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: PASS. Then add end-to-end coverage for incident timeline visibility, degraded recovery state, and demo-readiness blocked reasons.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/tests/e2e/trading-workspace.spec.ts README.md
git commit -m "feat: finalize e12 reliability coverage"
```

## Spec Coverage Check

- Degraded-mode entry reasons, visibility, blocked features, and confidence policy are covered by Tasks 1, 2, and 5.
- Local fallback availability, limitations, and non-silent UI visibility are covered by Tasks 2 and 5.
- Readiness criteria for demo-stage and release evaluation are covered by Task 3.
- `HTTP + SSE` reliability routes and incident streaming are covered by Task 4.
- Workspace visibility for degraded state, incident timeline, readiness checklist, and release gates is covered by Tasks 5 and 6.

## Assumptions

- `E7`, `E8`, `E9`, and `E11` remain the canonical upstream sources for session discipline, demo evidence, audit/review evidence, and validation summaries.
- Reliability state is authored by backend truth; frontend only renders it and responds to stream updates.
- The route and file structure remain provisional until later demo-stage cleanup.

## Execution Handoff

Plan complete and saved to `implementation_plans/e12-reliability-degraded-mode-and-release-readiness-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
