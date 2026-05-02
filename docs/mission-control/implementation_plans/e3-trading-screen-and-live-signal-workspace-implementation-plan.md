# E3 Trading Screen And Live Signal Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working `E3` analyst-first `Trading Workspace` for `CLAY Mission Control`: one focused pair, active signals, monitoring pool, situation map, reasoning/risk/news context, briefing handoff, and live state updates over `HTTP + SSE`.

**Architecture:** The implementation extends the provisional `E1` app repository with a dedicated workspace domain across backend and frontend. The backend serves snapshot bootstrap endpoints, operator commands, and `SSE` event streams backed by `E1` runtime state and `E2` freshness/storage contracts. The frontend composes the approved `v15` UI baseline into production-ready route modules and state stores while preserving the central rule: one dominant pair in focus, surrounding context secondary, and no exchange-terminal clone behavior.

**Tech Stack:** React 19, TypeScript 5.x, Vite, React Router, Zustand, TanStack Query, FastAPI, Pydantic v2, pytest, Vitest, Testing Library, Playwright, Server-Sent Events

---

## Repository Root

This plan assumes the working application repository will live at:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app`

Important:

- this is still a `provisional implementation layout`;
- the current file layout is allowed to evolve after demo/paper-trading validation;
- until then, prefer stable module boundaries over premature directory perfectionism with cathedral-grade folder bikeshedding.

## UI Baseline Reference

This plan intentionally reuses the approved `v15` UI archive as the baseline visual and structural reference:

`/home/emma/Documents/Obsidian/CachyOS/Trading/clay-mission-control_ui_v15.zip`

Useful component anchors already present in that baseline:

- `src/App.tsx`
- `src/components/TradingWorkspace.tsx`
- `src/components/SignalList.tsx`
- `src/components/PreflightBriefing.tsx`
- `src/components/Sidebar.tsx`
- `src/types.ts`
- `src/mockData.ts`

These files are reference material for structure and interaction semantics, not immutable final production paths.

## File Structure

### Backend

- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/workspace.py`
- Create: `backend/src/clay_mc/api/routes/workspace_stream.py`
- Create: `backend/src/clay_mc/workspace/models.py`
- Create: `backend/src/clay_mc/workspace/service.py`
- Create: `backend/src/clay_mc/workspace/streaming.py`
- Create: `backend/src/clay_mc/workspace/mapper.py`
- Create: `backend/tests/api/test_workspace_api.py`
- Create: `backend/tests/api/test_workspace_stream.py`
- Create: `backend/tests/workspace/test_workspace_service.py`

### Frontend

- Modify: `frontend/package.json`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/app/router.tsx`
- Create: `frontend/src/types/workspace.ts`
- Create: `frontend/src/api/workspace-client.ts`
- Create: `frontend/src/stores/workspace-store.ts`
- Create: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Create: `frontend/src/features/workspace/components/active-signals-panel.tsx`
- Create: `frontend/src/features/workspace/components/monitoring-pool-panel.tsx`
- Create: `frontend/src/features/workspace/components/focused-pair-header.tsx`
- Create: `frontend/src/features/workspace/components/situation-map.tsx`
- Create: `frontend/src/features/workspace/components/reasoning-panel.tsx`
- Create: `frontend/src/features/workspace/components/risk-panel.tsx`
- Create: `frontend/src/features/workspace/components/news-sentiment-panel.tsx`
- Create: `frontend/src/features/workspace/components/workspace-state-banner.tsx`
- Create: `frontend/src/features/workspace/components/no-active-signal-state.tsx`
- Create: `frontend/src/features/workspace/components/update-meta-strip.tsx`
- Create: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/briefing/briefing-handoff.ts`
- Create: `frontend/src/features/workspace/trading-workspace-route.test.tsx`
- Create: `frontend/src/features/workspace/workspace-store.test.ts`
- Create: `frontend/tests/e2e/trading-workspace.spec.ts`

### Repo-level

- Modify: `README.md`

---

### Task 1: Establish Workspace Domain Contracts Across Backend And Frontend

**Files:**
- Create: `backend/src/clay_mc/workspace/models.py`
- Create: `frontend/src/types/workspace.ts`
- Create: `backend/tests/workspace/test_workspace_service.py`
- Create: `frontend/src/features/workspace/workspace-store.test.ts`

- [ ] **Step 1: Write the failing contract tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/workspace/test_workspace_service.py
from clay_mc.workspace.models import WorkspaceStateSnapshot


def test_workspace_state_snapshot_contains_required_e3_fields() -> None:
    snapshot = WorkspaceStateSnapshot.model_validate(
        {
            "runtime_state": "active_session",
            "workspace_posture": "normal",
            "focused_signal_state": "active",
            "can_open_binance": True,
            "can_log_decision": True,
            "blocking_reason": None,
        }
    )

    assert snapshot.runtime_state == "active_session"
    assert snapshot.workspace_posture == "normal"
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/workspace-store.test.ts
import { describe, expect, it } from 'vitest'
import type { WorkspaceSnapshot } from '../../types/workspace'

describe('workspace contracts', () => {
  it('defines the minimum snapshot shape for E3', () => {
    const snapshot: WorkspaceSnapshot = {
      focusPair: {
        symbol: 'BTCUSDT',
        displayName: 'BTC / USDT',
        isFocused: true,
        role: 'primary',
        lastPrice: 70250.1,
        pctChange24h: 2.3,
        volatility: 0.61,
        lastScanAt: '2026-04-15T09:30:00Z',
        activeSignalId: 'sig-1',
        focusSource: 'briefing',
      },
      workspaceState: {
        runtimeState: 'active_session',
        workspacePosture: 'normal',
        focusedSignalState: 'active',
        canOpenBinance: true,
        canLogDecision: true,
        blockingReason: null,
      },
      signals: [],
      monitoringPool: [],
    }

    expect(snapshot.focusPair.focusSource).toBe('briefing')
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/workspace/test_workspace_service.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test workspace-store.test.ts --run
```

Expected: FAIL because the workspace domain models do not exist yet.

- [ ] **Step 3: Implement shared workspace contracts**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/workspace/models.py
from pydantic import BaseModel


class FocusPairSnapshot(BaseModel):
    symbol: str
    display_name: str
    is_focused: bool
    role: str
    last_price: float
    pct_change_24h: float
    volatility: float
    last_scan_at: str
    active_signal_id: str | None
    focus_source: str


class WorkspaceStateSnapshot(BaseModel):
    runtime_state: str
    workspace_posture: str
    focused_signal_state: str
    can_open_binance: bool
    can_log_decision: bool
    blocking_reason: str | None
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/types/workspace.ts
export type RuntimeState =
  | 'background_monitoring'
  | 'pre_session'
  | 'active_session'
  | 'paused'
  | 'review'
  | 'degraded'

export type WorkspacePosture =
  | 'normal'
  | 'monitoring_only'
  | 'defensive'
  | 'restricted_by_degraded'

export type FocusSource =
  | 'briefing'
  | 'signal_click'
  | 'monitoring_click'
  | 'system_recommendation'

export interface FocusPairSnapshot {
  symbol: string
  displayName: string
  isFocused: boolean
  role: 'primary' | 'backup' | 'monitoring'
  lastPrice: number
  pctChange24h: number
  volatility: number
  lastScanAt: string
  activeSignalId: string | null
  focusSource: FocusSource
}

export interface WorkspaceStateSnapshot {
  runtimeState: RuntimeState
  workspacePosture: WorkspacePosture
  focusedSignalState: 'active' | 'weakening' | 'invalidated' | 'absent'
  canOpenBinance: boolean
  canLogDecision: boolean
  blockingReason: string | null
}

export interface WorkspaceSnapshot {
  focusPair: FocusPairSnapshot
  workspaceState: WorkspaceStateSnapshot
  signals: WorkspaceSignalSummary[]
  monitoringPool: MonitoringPoolItem[]
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/workspace/test_workspace_service.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test workspace-store.test.ts --run
```

Expected: PASS with the minimum `E3` domain vocabulary now encoded in both backend and frontend.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/workspace frontend/src/types/workspace.ts backend/tests/workspace frontend/src/features/workspace/workspace-store.test.ts
git commit -m "feat: add e3 workspace domain contracts"
```

### Task 2: Build Workspace Snapshot API And Bootstrap Mapper

**Files:**
- Create: `backend/src/clay_mc/workspace/service.py`
- Create: `backend/src/clay_mc/workspace/mapper.py`
- Create: `backend/src/clay_mc/api/routes/workspace.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/api/test_workspace_api.py`

- [ ] **Step 1: Write the failing API bootstrap tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_workspace_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_trading_workspace_snapshot_returns_focus_pair_and_state() -> None:
    client = TestClient(app)

    response = client.get("/workspace/trading")

    assert response.status_code == 200
    payload = response.json()
    assert payload["focusPair"]["symbol"] == "BTCUSDT"
    assert payload["workspaceState"]["runtimeState"] == "active_session"


def test_trading_focus_endpoint_returns_current_focus_snapshot() -> None:
    client = TestClient(app)

    response = client.get("/workspace/trading/focus")

    assert response.status_code == 200
    assert response.json()["focusPair"]["focusSource"] == "briefing"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_workspace_api.py -v
```

Expected: FAIL because the workspace routes do not exist yet.

- [ ] **Step 3: Implement snapshot service, mapper, and routes**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/workspace/service.py
from clay_mc.workspace.models import WorkspaceStateSnapshot


def build_demo_workspace_state() -> WorkspaceStateSnapshot:
    return WorkspaceStateSnapshot(
        runtime_state="active_session",
        workspace_posture="normal",
        focused_signal_state="active",
        can_open_binance=True,
        can_log_decision=True,
        blocking_reason=None,
    )
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/workspace/mapper.py
from clay_mc.workspace.models import FocusPairSnapshot


def build_demo_focus_pair() -> FocusPairSnapshot:
    return FocusPairSnapshot(
        symbol="BTCUSDT",
        display_name="BTC / USDT",
        is_focused=True,
        role="primary",
        last_price=70250.10,
        pct_change_24h=2.3,
        volatility=0.61,
        last_scan_at="2026-04-15T09:30:00Z",
        active_signal_id="sig-1",
        focus_source="briefing",
    )
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/workspace.py
from fastapi import APIRouter

from clay_mc.workspace.mapper import build_demo_focus_pair
from clay_mc.workspace.service import build_demo_workspace_state


router = APIRouter(prefix="/workspace/trading", tags=["workspace"])


@router.get("")
def get_trading_workspace_snapshot() -> dict[str, object]:
    return {
        "focusPair": build_demo_focus_pair().model_dump(by_alias=False),
        "workspaceState": {
            "runtimeState": "active_session",
            "workspacePosture": "normal",
            "focusedSignalState": "active",
            "canOpenBinance": True,
            "canLogDecision": True,
            "blockingReason": None,
        },
        "signals": [],
        "monitoringPool": [],
    }


@router.get("/focus")
def get_trading_focus() -> dict[str, object]:
    return {"focusPair": get_trading_workspace_snapshot()["focusPair"]}
```

- [ ] **Step 4: Run the API tests and add snapshot fields**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_workspace_api.py -v
```

Expected: PASS with bootstrap routes for `GET /workspace/trading` and `GET /workspace/trading/focus`. Extend the payload to include `signals`, `monitoringPool`, `reasoning`, `risk`, `news`, and `freshness`.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api backend/src/clay_mc/workspace backend/tests/api/test_workspace_api.py
git commit -m "feat: add workspace snapshot bootstrap routes"
```

### Task 3: Build The Frontend Trading Workspace Route And Focus Sync Store

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/app/router.tsx`
- Create: `frontend/src/api/workspace-client.ts`
- Create: `frontend/src/stores/workspace-store.ts`
- Create: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Create: `frontend/src/features/workspace/trading-workspace-route.test.tsx`

- [ ] **Step 1: Write the failing route and store tests**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/trading-workspace-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TradingWorkspaceRoute } from './trading-workspace-route'

describe('TradingWorkspaceRoute', () => {
  it('renders active signals and monitoring pool regions', () => {
    render(<TradingWorkspaceRoute />)

    expect(screen.getByText('Active Signals')).toBeInTheDocument()
    expect(screen.getByText('Monitoring Pool')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: FAIL because the route and store do not exist yet.

- [ ] **Step 3: Implement the workspace client, store, and route shell**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/stores/workspace-store.ts
import { create } from 'zustand'

type WorkspaceStore = {
  focusPairSymbol: string
  selectedSignalId: string | null
  setFocusPairSymbol: (symbol: string) => void
  setSelectedSignalId: (signalId: string | null) => void
}

export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  focusPairSymbol: 'BTCUSDT',
  selectedSignalId: 'sig-1',
  setFocusPairSymbol: (symbol) => set({ focusPairSymbol: symbol }),
  setSelectedSignalId: (signalId) => set({ selectedSignalId: signalId }),
}))
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/trading-workspace-route.tsx
export function TradingWorkspaceRoute() {
  return (
    <main className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <section aria-label="active-signals">
        <h2>Active Signals</h2>
      </section>
      <section aria-label="workspace-main" className="grid gap-4">
        <div>
          <h2>Monitoring Pool</h2>
        </div>
      </section>
    </main>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/App.tsx
import { RouterProvider } from 'react-router-dom'

import { appRouter } from './app/router'

export default function App() {
  return <RouterProvider router={appRouter} />
}
```

- [ ] **Step 4: Run the tests and wire snapshot loading**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: PASS. Then add `TanStack Query` bootstrap loading from `GET /workspace/trading` and keep `focusPairSymbol` / `selectedSignalId` synchronized in one store.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/App.tsx frontend/src/app frontend/src/api frontend/src/stores frontend/src/features/workspace
git commit -m "feat: add trading workspace route shell and focus store"
```

### Task 4: Implement Active Signals, Monitoring Pool, And Focus Synchronization

**Files:**
- Create: `frontend/src/features/workspace/components/active-signals-panel.tsx`
- Create: `frontend/src/features/workspace/components/monitoring-pool-panel.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Create: `frontend/src/features/workspace/workspace-store.test.ts`

- [ ] **Step 1: Write the failing focus sync tests**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/workspace-store.test.ts
import { describe, expect, it } from 'vitest'

import { useWorkspaceStore } from '../../stores/workspace-store'

describe('workspace focus sync', () => {
  it('updates focus pair when an active signal is selected', () => {
    const store = useWorkspaceStore.getState()

    store.setSelectedSignalId('sig-2')
    store.setFocusPairSymbol('SOLUSDT')

    expect(useWorkspaceStore.getState().focusPairSymbol).toBe('SOLUSDT')
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test workspace-store.test.ts --run
```

Expected: FAIL because selection logic has not been wired into components yet.

- [ ] **Step 3: Implement signal and monitoring panels**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/components/active-signals-panel.tsx
import type { WorkspaceSignalSummary } from '../../../types/workspace'

type Props = {
  signals: WorkspaceSignalSummary[]
  selectedSignalId: string | null
  onSelect: (signalId: string, symbol: string) => void
}

export function ActiveSignalsPanel({ signals, selectedSignalId, onSelect }: Props) {
  return (
    <section>
      <h2>Active Signals</h2>
      <ul>
        {signals.map((signal) => (
          <li key={signal.signalId}>
            <button
              type="button"
              data-selected={selectedSignalId === signal.signalId}
              onClick={() => onSelect(signal.signalId, signal.pair)}
            >
              {signal.pair} · {signal.direction} · {signal.state}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/components/monitoring-pool-panel.tsx
import type { MonitoringPoolItem } from '../../../types/workspace'

type Props = {
  items: MonitoringPoolItem[]
  onSelectPair: (symbol: string) => void
}

export function MonitoringPoolPanel({ items, onSelectPair }: Props) {
  return (
    <section>
      <h2>Monitoring Pool</h2>
      <ul>
        {items.map((item) => (
          <li key={item.symbol}>
            <button type="button" onClick={() => onSelectPair(item.symbol)}>
              {item.symbol} · {item.role} · {item.availabilityStatus}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
```

- [ ] **Step 4: Run the tests and add `no_active_signal` transition coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test workspace-store.test.ts trading-workspace-route.test.tsx --run
```

Expected: PASS. Add follow-up UI tests proving that clicking a monitoring item without an active signal switches the workspace into `focusedSignalState = 'absent'` instead of leaking stale signal content.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/features/workspace/components frontend/src/features/workspace/trading-workspace-route.tsx frontend/src/features/workspace/workspace-store.test.ts
git commit -m "feat: add signal and monitoring focus sync"
```

### Task 5: Implement Focused Pair Header, Situation Map, And Context Panels

**Files:**
- Create: `frontend/src/features/workspace/components/focused-pair-header.tsx`
- Create: `frontend/src/features/workspace/components/situation-map.tsx`
- Create: `frontend/src/features/workspace/components/reasoning-panel.tsx`
- Create: `frontend/src/features/workspace/components/risk-panel.tsx`
- Create: `frontend/src/features/workspace/components/news-sentiment-panel.tsx`
- Create: `frontend/src/features/workspace/components/no-active-signal-state.tsx`
- Create: `frontend/src/features/workspace/components/update-meta-strip.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Create: `frontend/src/features/workspace/trading-workspace-route.test.tsx`

- [ ] **Step 1: Write the failing rendering tests for main panels**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/trading-workspace-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TradingWorkspaceRoute } from './trading-workspace-route'

describe('TradingWorkspaceRoute panels', () => {
  it('renders the analyst-first main sections', () => {
    render(<TradingWorkspaceRoute />)

    expect(screen.getByText('Analyst Situation Map')).toBeInTheDocument()
    expect(screen.getByText('AI Reasoning & Context')).toBeInTheDocument()
    expect(screen.getByText('Risk Assessment')).toBeInTheDocument()
    expect(screen.getByText('News & Sentiment')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: FAIL because the main analyst panels do not exist yet.

- [ ] **Step 3: Implement the main analyst-first sections**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/components/situation-map.tsx
type Props = {
  pair: string
  signalState: 'active' | 'weakening' | 'invalidated' | 'absent'
}

export function SituationMap({ pair, signalState }: Props) {
  return (
    <section>
      <h2>Analyst Situation Map</h2>
      <p>{pair}</p>
      <p>Signal state: {signalState}</p>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/components/reasoning-panel.tsx
export function ReasoningPanel() {
  return (
    <section>
      <h2>AI Reasoning & Context</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/components/risk-panel.tsx
export function RiskPanel() {
  return (
    <section>
      <h2>Risk Assessment</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/components/news-sentiment-panel.tsx
export function NewsSentimentPanel() {
  return (
    <section>
      <h2>News & Sentiment</h2>
    </section>
  )
}
```

- [ ] **Step 4: Run the tests and add `no_active_signal` rendering**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: PASS. Then add a second test and component branch proving that when the focused pair has no active signal, the route renders a monitoring-oriented neutral state instead of stale target/stop/explanation values.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/features/workspace/components frontend/src/features/workspace/trading-workspace-route.tsx frontend/src/features/workspace/trading-workspace-route.test.tsx
git commit -m "feat: add workspace main analyst panels"
```

### Task 6: Add Briefing Handoff, Workspace State Banner, And SSE Updates

**Files:**
- Create: `backend/src/clay_mc/api/routes/workspace_stream.py`
- Create: `backend/src/clay_mc/workspace/streaming.py`
- Create: `backend/tests/api/test_workspace_stream.py`
- Create: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/workspace/components/workspace-state-banner.tsx`
- Create: `frontend/src/features/briefing/briefing-handoff.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Create: `frontend/tests/e2e/trading-workspace.spec.ts`

- [ ] **Step 1: Write the failing stream and handoff tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_workspace_stream.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_workspace_stream_returns_event_stream_response() -> None:
    client = TestClient(app)

    response = client.get("/workspace/trading/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/tests/e2e/trading-workspace.spec.ts
import { expect, test } from '@playwright/test'

test('briefing handoff lands on the focused pair workspace', async ({ page }) => {
  await page.goto('/trading')

  await expect(page.getByText('BTC / USDT')).toBeVisible()
  await expect(page.getByText('Analyst Situation Map')).toBeVisible()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_workspace_stream.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: FAIL because the stream endpoint and briefing handoff are not implemented yet.

- [ ] **Step 3: Implement SSE and briefing handoff glue**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/workspace_stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/workspace/trading", tags=["workspace-stream"])


def event_lines():
    yield "event: workspace_state\n"
    yield 'data: {"runtimeState":"active_session","workspacePosture":"normal"}\n\n'


@router.get("/stream")
def get_workspace_stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream")
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/briefing/briefing-handoff.ts
export type BriefingHandoff = {
  primaryFocusPair: string
  backupPairs: string[]
  activeStrategy: string
  activeModelContext: string
  workspacePosture: 'normal' | 'defensive'
}

export function applyBriefingHandoff(input: BriefingHandoff) {
  return {
    focusPairSymbol: input.primaryFocusPair,
    monitoringPoolSymbols: input.backupPairs,
    workspacePosture: input.workspacePosture,
  }
}
```

- [ ] **Step 4: Run the tests and add degraded/paused UI semantics**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_workspace_stream.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: PASS. Then extend the event stream and banner rendering so `degraded`, `defensive`, `paused`, and `invalidated` each show distinct treatment and never masquerade as normal mode.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api/routes/workspace_stream.py backend/src/clay_mc/workspace/streaming.py backend/tests/api/test_workspace_stream.py frontend/src/features/workspace/hooks frontend/src/features/workspace/components/workspace-state-banner.tsx frontend/src/features/briefing frontend/tests/e2e/trading-workspace.spec.ts
git commit -m "feat: add workspace streaming and briefing handoff"
```

### Task 7: Add Operator Actions, Secondary Binance Action, And Documentation Pass

**Files:**
- Modify: `backend/src/clay_mc/api/routes/workspace.py`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/components/focused-pair-header.tsx`
- Modify: `README.md`
- Create: `frontend/tests/e2e/trading-workspace.spec.ts`

- [ ] **Step 1: Write the failing operator action tests**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/tests/e2e/trading-workspace.spec.ts
import { expect, test } from '@playwright/test'

test('open on binance remains a secondary action', async ({ page }) => {
  await page.goto('/trading')

  await expect(page.getByRole('button', { name: /open on binance/i })).toBeVisible()
  await expect(page.getByText('Analyst Situation Map')).toBeVisible()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: FAIL because the external action and final route wiring are not complete yet.

- [ ] **Step 3: Implement operator actions and final route wiring**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/workspace.py
from pydantic import BaseModel


class FocusCommand(BaseModel):
    symbol: str
    source: str


@router.post("/focus")
def set_focus_pair(command: FocusCommand) -> dict[str, object]:
    return {"accepted": True, "symbol": command.symbol, "source": command.source}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/components/focused-pair-header.tsx
type Props = {
  symbol: string
  onOpenBinance: () => void
}

export function FocusedPairHeader({ symbol, onOpenBinance }: Props) {
  return (
    <header>
      <h1>{symbol.replace('USDT', ' / USDT')}</h1>
      <button type="button" onClick={onOpenBinance}>
        Open on Binance
      </button>
    </header>
  )
}
```

- [ ] **Step 4: Run the tests and complete documentation**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: PASS. Update `README.md` with workspace snapshot endpoints, `SSE` stream notes, route entry points, and a short warning that the product is analyst-support software, not auto-execution.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api/routes/workspace.py frontend/src/features/workspace frontend/tests/e2e/trading-workspace.spec.ts README.md
git commit -m "feat: finalize e3 workspace operator flow"
```

## Spec Coverage Check

- One dominant `focused pair` and surrounding context are covered by Tasks 3, 4, and 5.
- `Active Signals`, `Monitoring Pool`, `Focused Pair Header`, `Situation Map`, `Reasoning`, `Risk`, `News`, and freshness metadata are covered by Tasks 4 and 5.
- `no_active_signal` behavior and stale-context protection are covered by Tasks 4, 5, and 6.
- `HTTP + SSE` transport expectations and bootstrap/live-update split are covered by Tasks 2 and 6.
- `Briefing -> Workspace` handoff is covered by Task 6.
- Operator actions and the secondary `Open on Binance` action are covered by Task 7.
- The plan explicitly avoids exchange-terminal scope creep and keeps `E3` dependent on `E1 + E2` rather than re-implementing signal or ingestion internals.

## Assumptions

- `E1` and `E2` implementation plans remain the canonical upstream prerequisites.
- The approved `v15` UI archive is the design baseline for layout intent and component vocabulary, but not a mandatory copy-paste implementation source.
- The frontend route structure may later be normalized during a post-demo architectural cleanup without changing the underlying contracts.
- Final ranking, risk computation, and signal lifecycle internals remain downstream responsibilities of `E6`, not `E3`.

## Execution Handoff

Plan complete and saved to `implementation_plans/e3-trading-screen-and-live-signal-workspace-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
