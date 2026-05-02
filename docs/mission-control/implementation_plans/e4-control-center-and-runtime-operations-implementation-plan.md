# E4 Control Center And Runtime Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working `E4` operator-facing `Control Center` for `CLAY Mission Control`: runtime and service health visibility, incidents, active configuration summaries, model/provider status, safe operator actions, and live operational updates over `HTTP + SSE`.

**Architecture:** The implementation extends the provisional `E1` repository with a dedicated `control-center` domain across backend and frontend. Backend routes expose operational snapshots, action review/apply endpoints, and `SSE` event feeds backed by `E1` runtime-manager, `E2` ingest/health status, and `ADR-002` config validation rules. The frontend adds a system-control route that is clearly distinct from `Trading Workspace`: it prioritizes runtime readiness, service/actionability, incident triage, and review-confirm flows over pair/signal analysis.

**Tech Stack:** React 19, TypeScript 5.x, Vite, React Router, Zustand, TanStack Query, FastAPI, Pydantic v2, pytest, Vitest, Testing Library, Playwright, Server-Sent Events

---

## Repository Root

This plan assumes the working application repository will live at:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app`

Important:

- this remains a `provisional implementation layout`;
- post-demo structural cleanup is still allowed and expected;
- until then, prioritize stable control-plane boundaries over perfect folder feng shui.

## File Structure

### Backend

- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/control_center.py`
- Create: `backend/src/clay_mc/api/routes/control_center_stream.py`
- Create: `backend/src/clay_mc/control_center/models.py`
- Create: `backend/src/clay_mc/control_center/service.py`
- Create: `backend/src/clay_mc/control_center/actions.py`
- Create: `backend/src/clay_mc/control_center/streaming.py`
- Create: `backend/tests/api/test_control_center_api.py`
- Create: `backend/tests/api/test_control_center_stream.py`
- Create: `backend/tests/control_center/test_action_policy.py`

### Frontend

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/app/router.tsx`
- Create: `frontend/src/types/control-center.ts`
- Create: `frontend/src/api/control-center-client.ts`
- Create: `frontend/src/stores/control-center-store.ts`
- Create: `frontend/src/features/control-center/control-center-route.tsx`
- Create: `frontend/src/features/control-center/components/system-health-panel.tsx`
- Create: `frontend/src/features/control-center/components/managed-services-panel.tsx`
- Create: `frontend/src/features/control-center/components/runtime-status-panel.tsx`
- Create: `frontend/src/features/control-center/components/alerts-audit-panel.tsx`
- Create: `frontend/src/features/control-center/components/active-configuration-panel.tsx`
- Create: `frontend/src/features/control-center/components/model-provider-panel.tsx`
- Create: `frontend/src/features/control-center/components/runtime-console-drawer.tsx`
- Create: `frontend/src/features/control-center/components/action-review-dialog.tsx`
- Create: `frontend/src/features/control-center/components/control-center-state-banner.tsx`
- Create: `frontend/src/features/control-center/hooks/use-control-center-stream.ts`
- Create: `frontend/src/features/control-center/control-center-route.test.tsx`
- Create: `frontend/src/features/control-center/control-center-store.test.ts`
- Create: `frontend/tests/e2e/control-center.spec.ts`

### Repo-level

- Modify: `README.md`

---

### Task 1: Establish Control Center Domain Contracts

**Files:**
- Create: `backend/src/clay_mc/control_center/models.py`
- Create: `frontend/src/types/control-center.ts`
- Create: `backend/tests/control_center/test_action_policy.py`
- Create: `frontend/src/features/control-center/control-center-store.test.ts`

- [ ] **Step 1: Write the failing contract tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/control_center/test_action_policy.py
from clay_mc.control_center.models import GlobalHealthSummary


def test_global_health_summary_contains_runtime_and_actionability_fields() -> None:
    summary = GlobalHealthSummary.model_validate(
        {
            "runtime_state": "active_session",
            "overall_status": "degraded",
            "actionability": "limited",
            "active_incident_count": 2,
            "critical_incident_count": 1,
            "last_status_refresh_at": "2026-04-15T10:00:00Z",
            "blocking_reason": None,
        }
    )

    assert summary.overall_status == "degraded"
    assert summary.actionability == "limited"
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/control-center/control-center-store.test.ts
import { describe, expect, it } from 'vitest'
import type { ControlCenterSnapshot } from '../../types/control-center'

describe('control center contracts', () => {
  it('defines the minimum snapshot shape for E4', () => {
    const snapshot: ControlCenterSnapshot = {
      summary: {
        runtimeState: 'active_session',
        overallStatus: 'degraded',
        actionability: 'limited',
        activeIncidentCount: 2,
        criticalIncidentCount: 1,
        lastStatusRefreshAt: '2026-04-15T10:00:00Z',
        blockingReason: null,
      },
      services: [],
      incidents: [],
      config: null,
      models: [],
    }

    expect(snapshot.summary.overallStatus).toBe('degraded')
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/control_center/test_action_policy.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test control-center-store.test.ts --run
```

Expected: FAIL because the `control_center` domain models do not exist yet.

- [ ] **Step 3: Implement shared control-center contracts**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/control_center/models.py
from pydantic import BaseModel


class GlobalHealthSummary(BaseModel):
    runtime_state: str
    overall_status: str
    actionability: str
    active_incident_count: int
    critical_incident_count: int
    last_status_refresh_at: str
    blocking_reason: str | None


class ServiceCardSnapshot(BaseModel):
    service_id: str
    service_name: str
    service_kind: str
    lifecycle_class: str
    status: str
    last_heartbeat_at: str | None
    last_error: str | None
    latency_ms: int | None
    freshness_status: str | None
    allowed_actions: list[str]
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/types/control-center.ts
export type OverallStatus = 'healthy' | 'degraded' | 'stale' | 'stopped' | 'error'
export type Actionability = 'normal' | 'limited' | 'blocked'

export interface GlobalHealthSummary {
  runtimeState: 'background_monitoring' | 'pre_session' | 'active_session' | 'paused' | 'review' | 'degraded'
  overallStatus: OverallStatus
  actionability: Actionability
  activeIncidentCount: number
  criticalIncidentCount: number
  lastStatusRefreshAt: string
  blockingReason: string | null
}

export interface ServiceCardSnapshot {
  serviceId: string
  serviceName: string
  serviceKind: string
  lifecycleClass: 'always_on' | 'background_critical' | 'on_demand'
  status: 'healthy' | 'degraded' | 'stale' | 'stopped' | 'error' | 'disabled'
  lastHeartbeatAt: string | null
  lastError: string | null
  latencyMs: number | null
  freshnessStatus: string | null
  allowedActions: string[]
}

export interface ControlCenterSnapshot {
  summary: GlobalHealthSummary
  services: ServiceCardSnapshot[]
  incidents: IncidentSnapshot[]
  config: ActiveConfigurationSnapshot | null
  models: ModelAssignmentSummary[]
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/control_center/test_action_policy.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test control-center-store.test.ts --run
```

Expected: PASS with the minimum `E4` vocabulary encoded on both sides.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/control_center frontend/src/types/control-center.ts backend/tests/control_center frontend/src/features/control-center/control-center-store.test.ts
git commit -m "feat: add e4 control center domain contracts"
```

### Task 2: Build Control Center Snapshot API And Health Aggregator

**Files:**
- Create: `backend/src/clay_mc/control_center/service.py`
- Create: `backend/src/clay_mc/api/routes/control_center.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/api/test_control_center_api.py`

- [ ] **Step 1: Write the failing control center API tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_control_center_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_control_center_overview_returns_summary_and_services() -> None:
    client = TestClient(app)

    response = client.get("/control-center/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["runtimeState"] == "active_session"
    assert len(payload["services"]) > 0


def test_control_center_incidents_endpoint_returns_recent_incidents() -> None:
    client = TestClient(app)

    response = client.get("/control-center/incidents")

    assert response.status_code == 200
    assert "items" in response.json()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_control_center_api.py -v
```

Expected: FAIL because the `control-center` routes do not exist yet.

- [ ] **Step 3: Implement the overview service and routes**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/control_center/service.py
def build_demo_control_center_snapshot() -> dict[str, object]:
    return {
        "summary": {
            "runtimeState": "active_session",
            "overallStatus": "degraded",
            "actionability": "limited",
            "activeIncidentCount": 2,
            "criticalIncidentCount": 1,
            "lastStatusRefreshAt": "2026-04-15T10:00:00Z",
            "blockingReason": None,
        },
        "services": [
            {
                "serviceId": "market-data-service",
                "serviceName": "Market Data Service",
                "serviceKind": "ingestion",
                "lifecycleClass": "always_on",
                "status": "healthy",
                "lastHeartbeatAt": "2026-04-15T10:00:00Z",
                "lastError": None,
                "latencyMs": 42,
                "freshnessStatus": "fresh",
                "allowedActions": ["restart"],
            }
        ],
        "incidents": [],
        "config": None,
        "models": [],
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/control_center.py
from fastapi import APIRouter

from clay_mc.control_center.service import build_demo_control_center_snapshot


router = APIRouter(prefix="/control-center", tags=["control-center"])


@router.get("/overview")
def get_control_center_overview() -> dict[str, object]:
    return build_demo_control_center_snapshot()


@router.get("/incidents")
def get_control_center_incidents() -> dict[str, object]:
    return {"items": build_demo_control_center_snapshot()["incidents"]}
```

- [ ] **Step 4: Run the tests and extend the payload**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_control_center_api.py -v
```

Expected: PASS. Extend the payload to include `config`, `models`, and richer incident/service fields from the `E4` build spec.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api backend/src/clay_mc/control_center backend/tests/api/test_control_center_api.py
git commit -m "feat: add control center overview routes"
```

### Task 3: Build The Frontend Control Center Route And Snapshot Store

**Files:**
- Modify: `frontend/src/app/router.tsx`
- Create: `frontend/src/api/control-center-client.ts`
- Create: `frontend/src/stores/control-center-store.ts`
- Create: `frontend/src/features/control-center/control-center-route.tsx`
- Create: `frontend/src/features/control-center/control-center-route.test.tsx`

- [ ] **Step 1: Write the failing route tests**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/control-center/control-center-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ControlCenterRoute } from './control-center-route'

describe('ControlCenterRoute', () => {
  it('renders the main control center sections', () => {
    render(<ControlCenterRoute />)

    expect(screen.getByText('System Health')).toBeInTheDocument()
    expect(screen.getByText('Managed Services')).toBeInTheDocument()
    expect(screen.getByText('Active Configuration')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test control-center-route.test.tsx --run
```

Expected: FAIL because the control center route does not exist yet.

- [ ] **Step 3: Implement the route shell and store**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/stores/control-center-store.ts
import { create } from 'zustand'

type ControlCenterStore = {
  selectedServiceId: string | null
  selectedAction: string | null
  setSelectedServiceId: (serviceId: string | null) => void
  setSelectedAction: (action: string | null) => void
}

export const useControlCenterStore = create<ControlCenterStore>((set) => ({
  selectedServiceId: null,
  selectedAction: null,
  setSelectedServiceId: (serviceId) => set({ selectedServiceId: serviceId }),
  setSelectedAction: (action) => set({ selectedAction: action }),
}))
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/control-center/control-center-route.tsx
export function ControlCenterRoute() {
  return (
    <main className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(340px,0.9fr)]">
      <section>
        <h2>System Health</h2>
      </section>
      <section>
        <h2>Managed Services</h2>
      </section>
      <section>
        <h2>Active Configuration</h2>
      </section>
    </main>
  )
}
```

- [ ] **Step 4: Run the tests and wire snapshot loading**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test control-center-route.test.tsx --run
```

Expected: PASS. Then add `TanStack Query` bootstrap loading from `GET /control-center/overview` and keep selected service/action state in one store.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/app/router.tsx frontend/src/api frontend/src/stores frontend/src/features/control-center
git commit -m "feat: add control center route shell"
```

### Task 4: Implement System Health, Services, And Runtime Status Panels

**Files:**
- Create: `frontend/src/features/control-center/components/system-health-panel.tsx`
- Create: `frontend/src/features/control-center/components/managed-services-panel.tsx`
- Create: `frontend/src/features/control-center/components/runtime-status-panel.tsx`
- Create: `frontend/src/features/control-center/components/control-center-state-banner.tsx`
- Modify: `frontend/src/features/control-center/control-center-route.tsx`
- Create: `frontend/src/features/control-center/control-center-route.test.tsx`

- [ ] **Step 1: Write the failing panel rendering tests**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/control-center/control-center-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ControlCenterRoute } from './control-center-route'

describe('ControlCenterRoute panels', () => {
  it('renders system health, runtime status, and services', () => {
    render(<ControlCenterRoute />)

    expect(screen.getByText('Runtime Status')).toBeInTheDocument()
    expect(screen.getByText('System Health')).toBeInTheDocument()
    expect(screen.getByText('Managed Services')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test control-center-route.test.tsx --run
```

Expected: FAIL because the detailed panels do not exist yet.

- [ ] **Step 3: Implement the main operational panels**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/control-center/components/system-health-panel.tsx
export function SystemHealthPanel() {
  return (
    <section>
      <h2>System Health</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/control-center/components/runtime-status-panel.tsx
export function RuntimeStatusPanel() {
  return (
    <section>
      <h2>Runtime Status</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/control-center/components/managed-services-panel.tsx
export function ManagedServicesPanel() {
  return (
    <section>
      <h2>Managed Services</h2>
    </section>
  )
}
```

- [ ] **Step 4: Run the tests and add state distinction coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test control-center-route.test.tsx --run
```

Expected: PASS. Then add UI tests proving that runtime state, service status, and actionability are rendered as distinct labels instead of one merged “status pill”.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/features/control-center/components frontend/src/features/control-center/control-center-route.tsx frontend/src/features/control-center/control-center-route.test.tsx
git commit -m "feat: add core control center operational panels"
```

### Task 5: Implement Alerts, Configuration, And Model/Provider Panels

**Files:**
- Create: `frontend/src/features/control-center/components/alerts-audit-panel.tsx`
- Create: `frontend/src/features/control-center/components/active-configuration-panel.tsx`
- Create: `frontend/src/features/control-center/components/model-provider-panel.tsx`
- Modify: `frontend/src/features/control-center/control-center-route.tsx`
- Create: `frontend/src/features/control-center/control-center-route.test.tsx`

- [ ] **Step 1: Write the failing panel coverage tests**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/control-center/control-center-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ControlCenterRoute } from './control-center-route'

describe('ControlCenterRoute supporting panels', () => {
  it('renders alerts, configuration, and model/provider sections', () => {
    render(<ControlCenterRoute />)

    expect(screen.getByText('Recent Alerts')).toBeInTheDocument()
    expect(screen.getByText('Active Configuration')).toBeInTheDocument()
    expect(screen.getByText('Model / Provider Status')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test control-center-route.test.tsx --run
```

Expected: FAIL because these support panels do not exist yet.

- [ ] **Step 3: Implement the support panels**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/control-center/components/alerts-audit-panel.tsx
export function AlertsAuditPanel() {
  return (
    <section>
      <h2>Recent Alerts</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/control-center/components/active-configuration-panel.tsx
export function ActiveConfigurationPanel() {
  return (
    <section>
      <h2>Active Configuration</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/control-center/components/model-provider-panel.tsx
export function ModelProviderPanel() {
  return (
    <section>
      <h2>Model / Provider Status</h2>
    </section>
  )
}
```

- [ ] **Step 4: Run the tests and add degraded fallback coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test control-center-route.test.tsx --run
```

Expected: PASS. Then add a follow-up test proving fallback-only model/provider assignments render as degraded/limited and do not masquerade as normal full-capability mode.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/features/control-center/components frontend/src/features/control-center/control-center-route.tsx frontend/src/features/control-center/control-center-route.test.tsx
git commit -m "feat: add control center support panels"
```

### Task 6: Implement Safe Operator Actions, Review Dialogs, And SSE Updates

**Files:**
- Create: `backend/src/clay_mc/control_center/actions.py`
- Create: `backend/src/clay_mc/control_center/streaming.py`
- Create: `backend/src/clay_mc/api/routes/control_center_stream.py`
- Create: `backend/tests/api/test_control_center_stream.py`
- Create: `frontend/src/features/control-center/components/runtime-console-drawer.tsx`
- Create: `frontend/src/features/control-center/components/action-review-dialog.tsx`
- Create: `frontend/src/features/control-center/hooks/use-control-center-stream.ts`
- Modify: `frontend/src/features/control-center/control-center-route.tsx`
- Create: `frontend/tests/e2e/control-center.spec.ts`

- [ ] **Step 1: Write the failing operator flow tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_control_center_stream.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_control_center_stream_returns_event_stream_response() -> None:
    client = TestClient(app)

    response = client.get("/control-center/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/tests/e2e/control-center.spec.ts
import { expect, test } from '@playwright/test'

test('restarting a service during active session requires visible review', async ({ page }) => {
  await page.goto('/control-center')

  await expect(page.getByText('Managed Services')).toBeVisible()
  await expect(page.getByText(/review/i)).toBeVisible()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_control_center_stream.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/control-center.spec.ts
```

Expected: FAIL because the stream endpoint and operator review flow do not exist yet.

- [ ] **Step 3: Implement action policy and streaming**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/control_center/actions.py
from pydantic import BaseModel


class OperatorActionReview(BaseModel):
    action_type: str
    target_id: str
    requires_confirmation: bool
    impact_summary: str
    allowed: bool
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/control_center_stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/control-center", tags=["control-center-stream"])


def event_lines():
    yield "event: control_center_status\n"
    yield 'data: {"overallStatus":"degraded","actionability":"limited"}\n\n'


@router.get("/stream")
def get_control_center_stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream")
```

- [ ] **Step 4: Run the tests and add blocked-action coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_control_center_stream.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/control-center.spec.ts
```

Expected: PASS. Then add UI and backend policy tests proving blocked/restricted actions cannot silently bypass review when runtime or config state makes them unsafe.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/control_center backend/src/clay_mc/api/routes/control_center_stream.py backend/tests/api/test_control_center_stream.py frontend/src/features/control-center frontend/tests/e2e/control-center.spec.ts
git commit -m "feat: add control center streaming and review actions"
```

## Spec Coverage Check

- `System Health`, `Managed Services`, `Runtime Status`, `Alerts`, `Active Configuration`, and `Model / Provider Status` are covered by Tasks 3, 4, and 5.
- Service state, provider/connector state, runtime state, and actionability separation are covered by Tasks 1, 4, and 6.
- Safe config operations and required review/confirm semantics are covered by Tasks 5 and 6.
- `HTTP + SSE` transport expectations are covered by Tasks 2 and 6.
- Operator-safe service actions and review flows are covered by Task 6.
- The plan keeps `Control Center` distinct from `Trading Workspace` and does not smuggle signal/ranking logic into `E4`.

## Assumptions

- `E1`, `E2`, and the new `E4 build-spec` remain the canonical upstream sources.
- This plan intentionally exposes model/provider visibility and review entrypoints without redefining the deeper orchestration logic that belongs to `E5`.
- The current route and file structure are provisional and may be normalized after demo validation without changing the domain contracts.

## Execution Handoff

Plan complete and saved to `implementation_plans/e4-control-center-and-runtime-operations-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
