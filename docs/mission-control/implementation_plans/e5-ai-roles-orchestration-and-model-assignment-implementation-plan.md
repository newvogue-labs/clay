> **Live-правда AI-слоя консолидирована в `blueprint-v1.md` §9–§10.**
> Этот документ — детальная planning-chain E5, сохраняется как история.

# E5 AI Roles, Orchestration And Model Assignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working `E5` AI orchestration layer for `CLAY Mission Control`: AI role contracts, provider/model abstraction, assignment registry, orchestration flow, conflict summaries, degraded fallback handling, and operator-reviewed model switching.

**Architecture:** The implementation extends the provisional `E1` repository with an `ai_orchestration` domain across backend and frontend. Backend services model provider adapters, model registry records, role assignments, orchestration traces, and review/apply flows backed by `ADR-005`. Frontend routes and panels surface model/provider visibility, assignment review cards, conflict summaries, and degraded fallback state without leaking vendor-specific chaos into the public UI contract.

**Tech Stack:** React 19, TypeScript 5.x, Vite, React Router, Zustand, TanStack Query, FastAPI, Pydantic v2, pytest, Vitest, Testing Library, Playwright, Server-Sent Events

---

## Repository Root

This plan assumes the working application repository will live at:

`~/Projects/clay/app`

Important:

- this remains a `provisional implementation layout`;
- paths and module grouping may still be normalized after demo validation;
- until then, keep AI-role boundaries explicit so the codebase does not mutate into a vendor shrine with a JSON altar.

## File Structure

### Backend

- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/ai_roles.py`
- Create: `backend/src/clay_mc/api/routes/ai_assignments.py`
- Create: `backend/src/clay_mc/api/routes/ai_stream.py`
- Create: `backend/src/clay_mc/ai_orchestration/models.py`
- Create: `backend/src/clay_mc/ai_orchestration/registry.py`
- Create: `backend/src/clay_mc/ai_orchestration/assignments.py`
- Create: `backend/src/clay_mc/ai_orchestration/orchestrator.py`
- Create: `backend/src/clay_mc/ai_orchestration/conflicts.py`
- Create: `backend/src/clay_mc/ai_orchestration/fallbacks.py`
- Create: `backend/src/clay_mc/ai_orchestration/provider_contracts.py`
- Create: `backend/src/clay_mc/ai_orchestration/streaming.py`
- Create: `backend/tests/api/test_ai_assignments_api.py`
- Create: `backend/tests/api/test_ai_stream.py`
- Create: `backend/tests/ai_orchestration/test_registry_models.py`
- Create: `backend/tests/ai_orchestration/test_assignment_validation.py`
- Create: `backend/tests/ai_orchestration/test_conflict_summary.py`

### Frontend

- Modify: `frontend/src/app/router.tsx`
- Create: `frontend/src/types/ai-orchestration.ts`
- Create: `frontend/src/api/ai-client.ts`
- Create: `frontend/src/stores/ai-assignments-store.ts`
- Create: `frontend/src/features/ai-control/ai-control-route.tsx`
- Create: `frontend/src/features/ai-control/components/role-assignment-panel.tsx`
- Create: `frontend/src/features/ai-control/components/model-registry-panel.tsx`
- Create: `frontend/src/features/ai-control/components/provider-status-panel.tsx`
- Create: `frontend/src/features/ai-control/components/assignment-review-card.tsx`
- Create: `frontend/src/features/ai-control/components/conflict-summary-panel.tsx`
- Create: `frontend/src/features/ai-control/components/fallback-status-banner.tsx`
- Create: `frontend/src/features/ai-control/hooks/use-ai-events-stream.ts`
- Create: `frontend/src/features/ai-control/ai-control-route.test.tsx`
- Create: `frontend/src/features/ai-control/ai-assignments-store.test.ts`
- Create: `frontend/tests/e2e/ai-control.spec.ts`

### Repo-level

- Modify: `README.md`

---

### Task 1: Establish AI Role, Model, And Assignment Contracts

**Files:**
- Create: `backend/src/clay_mc/ai_orchestration/models.py`
- Create: `frontend/src/types/ai-orchestration.ts`
- Create: `backend/tests/ai_orchestration/test_registry_models.py`
- Create: `frontend/src/features/ai-control/ai-assignments-store.test.ts`

- [ ] **Step 1: Write the failing contract tests**

```python
# ~/Projects/clay/app/backend/tests/ai_orchestration/test_registry_models.py
from clay_mc.ai_orchestration.models import ModelVersionRecord


def test_model_version_record_contains_role_compatibility_and_capabilities() -> None:
    record = ModelVersionRecord.model_validate(
        {
            "model_id": "chief-gpt-oss",
            "provider_id": "openrouter",
            "display_name": "Chief GPT OSS",
            "version_label": "2026-04",
            "role_compatibility": ["chief_agent"],
            "capabilities": ["text_generation", "structured_output", "reasoning_suitable"],
            "activation_status": "active",
        }
    )

    assert "chief_agent" in record.role_compatibility
    assert "reasoning_suitable" in record.capabilities
```

```ts
// ~/Projects/clay/app/frontend/src/features/ai-control/ai-assignments-store.test.ts
import { describe, expect, it } from 'vitest'
import type { AssignmentSummary } from '../../types/ai-orchestration'

describe('ai assignment contracts', () => {
  it('defines the minimum assignment summary shape', () => {
    const assignment: AssignmentSummary = {
      roleName: 'chief_agent',
      providerName: 'OpenRouter',
      modelName: 'Chief GPT OSS',
      modelVersion: '2026-04',
      availabilityStatus: 'healthy',
      fallbackOnly: false,
      degradedFallbackAllowed: true,
      capabilitySummary: ['text_generation', 'reasoning_suitable'],
    }

    expect(assignment.roleName).toBe('chief_agent')
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd ~/Projects/clay/app/backend
uv run pytest tests/ai_orchestration/test_registry_models.py -v

cd ~/Projects/clay/app/frontend
pnpm test ai-assignments-store.test.ts --run
```

Expected: FAIL because the `ai_orchestration` domain contracts do not exist yet.

- [ ] **Step 3: Implement shared AI orchestration contracts**

```python
# ~/Projects/clay/app/backend/src/clay_mc/ai_orchestration/models.py
from pydantic import BaseModel


class ProviderRecord(BaseModel):
    provider_id: str
    provider_type: str
    display_name: str
    enabled: bool
    availability_status: str
    supports_streaming: bool


class ModelVersionRecord(BaseModel):
    model_id: str
    provider_id: str
    display_name: str
    version_label: str
    role_compatibility: list[str]
    capabilities: list[str]
    activation_status: str
```

```ts
// ~/Projects/clay/app/frontend/src/types/ai-orchestration.ts
export interface AssignmentSummary {
  roleName: 'chief_agent' | 'market_scanner' | 'news_sentiment_agent' | 'forecast_model' | 'local_fallback_text'
  providerName: string
  modelName: string
  modelVersion: string
  availabilityStatus: 'healthy' | 'degraded' | 'error' | 'disabled'
  fallbackOnly: boolean
  degradedFallbackAllowed: boolean
  capabilitySummary: string[]
}

export interface ConflictSummary {
  conflictId: string
  rolesInvolved: string[]
  conflictType: string
  summary: string
  confidencePenalty: number
  visibilityLevel: 'info' | 'warning' | 'critical'
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd ~/Projects/clay/app/backend
uv run pytest tests/ai_orchestration/test_registry_models.py -v

cd ~/Projects/clay/app/frontend
pnpm test ai-assignments-store.test.ts --run
```

Expected: PASS with the minimum `E5` vocabulary now encoded in backend and frontend.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/clay/app
git add backend/src/clay_mc/ai_orchestration frontend/src/types/ai-orchestration.ts backend/tests/ai_orchestration frontend/src/features/ai-control/ai-assignments-store.test.ts
git commit -m "feat: add e5 ai orchestration contracts"
```

### Task 2: Build Model Registry And Assignment Validation Layer

**Files:**
- Create: `backend/src/clay_mc/ai_orchestration/registry.py`
- Create: `backend/src/clay_mc/ai_orchestration/assignments.py`
- Create: `backend/src/clay_mc/ai_orchestration/provider_contracts.py`
- Create: `backend/tests/ai_orchestration/test_assignment_validation.py`

- [ ] **Step 1: Write the failing assignment validation tests**

```python
# ~/Projects/clay/app/backend/tests/ai_orchestration/test_assignment_validation.py
import pytest

from clay_mc.ai_orchestration.assignments import AssignmentValidationError, validate_assignment


def test_validate_assignment_accepts_role_compatible_model() -> None:
    assignment = validate_assignment(
        role_name="chief_agent",
        model_record={
            "model_id": "chief-gpt-oss",
            "role_compatibility": ["chief_agent"],
            "capabilities": ["text_generation", "structured_output", "reasoning_suitable"],
        },
    )

    assert assignment["role_name"] == "chief_agent"


def test_validate_assignment_rejects_incompatible_model() -> None:
    with pytest.raises(AssignmentValidationError):
        validate_assignment(
            role_name="chief_agent",
            model_record={
                "model_id": "tiny-classifier",
                "role_compatibility": ["news_sentiment_agent"],
                "capabilities": ["classification_suitable"],
            },
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd ~/Projects/clay/app/backend
uv run pytest tests/ai_orchestration/test_assignment_validation.py -v
```

Expected: FAIL because assignment validation does not exist yet.

- [ ] **Step 3: Implement registry and validation helpers**

```python
# ~/Projects/clay/app/backend/src/clay_mc/ai_orchestration/assignments.py
class AssignmentValidationError(ValueError):
    pass


ROLE_REQUIREMENTS = {
    "chief_agent": {"text_generation", "structured_output", "reasoning_suitable"},
    "market_scanner": {"structured_output"},
    "news_sentiment_agent": {"summary_suitable", "classification_suitable"},
}


def validate_assignment(role_name: str, model_record: dict[str, object]) -> dict[str, object]:
    compatibility = set(model_record["role_compatibility"])
    capabilities = set(model_record["capabilities"])

    if role_name not in compatibility:
        raise AssignmentValidationError(f"model incompatible with role {role_name}")

    required = ROLE_REQUIREMENTS.get(role_name, set())
    if required and not required.intersection(capabilities):
        raise AssignmentValidationError(f"model lacks capabilities for role {role_name}")

    return {"role_name": role_name, "model_id": model_record["model_id"]}
```

```python
# ~/Projects/clay/app/backend/src/clay_mc/ai_orchestration/provider_contracts.py
from pydantic import BaseModel


class ProviderInvocationResult(BaseModel):
    request_id: str
    model_id: str
    finish_reason: str
    latency_ms: int
    error_category: str | None
```

- [ ] **Step 4: Run the tests and add fallback-eligibility coverage**

Run:

```bash
cd ~/Projects/clay/app/backend
uv run pytest tests/ai_orchestration/test_assignment_validation.py -v
```

Expected: PASS. Then add follow-up tests proving `fallback_only` and `degraded_fallback_allowed` are validated separately from ordinary full-mode assignments.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/clay/app
git add backend/src/clay_mc/ai_orchestration backend/tests/ai_orchestration/test_assignment_validation.py
git commit -m "feat: add ai registry and assignment validation"
```

### Task 3: Build AI Assignments API And Review Flow

**Files:**
- Create: `backend/src/clay_mc/api/routes/ai_roles.py`
- Create: `backend/src/clay_mc/api/routes/ai_assignments.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/api/test_ai_assignments_api.py`

- [ ] **Step 1: Write the failing assignments API tests**

```python
# ~/Projects/clay/app/backend/tests/api/test_ai_assignments_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_ai_assignments_endpoint_returns_role_assignments() -> None:
    client = TestClient(app)

    response = client.get("/ai/assignments")

    assert response.status_code == 200
    assert len(response.json()["items"]) > 0


def test_ai_assignment_review_endpoint_returns_review_card() -> None:
    client = TestClient(app)

    response = client.get("/ai/assignments/review/chief_agent")

    assert response.status_code == 200
    assert response.json()["roleName"] == "chief_agent"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd ~/Projects/clay/app/backend
uv run pytest tests/api/test_ai_assignments_api.py -v
```

Expected: FAIL because the AI assignment routes do not exist yet.

- [ ] **Step 3: Implement the AI assignment routes**

```python
# ~/Projects/clay/app/backend/src/clay_mc/api/routes/ai_assignments.py
from fastapi import APIRouter


router = APIRouter(prefix="/ai/assignments", tags=["ai-assignments"])


@router.get("")
def get_assignments() -> dict[str, object]:
    return {
        "items": [
            {
                "roleName": "chief_agent",
                "providerName": "OpenRouter",
                "modelName": "Chief GPT OSS",
                "modelVersion": "2026-04",
                "availabilityStatus": "healthy",
                "fallbackOnly": False,
                "degradedFallbackAllowed": True,
                "capabilitySummary": ["text_generation", "reasoning_suitable"],
            }
        ]
    }


@router.get("/review/{role_name}")
def get_assignment_review(role_name: str) -> dict[str, object]:
    return {
        "roleName": role_name,
        "currentAssignment": "chief-gpt-oss",
        "proposedAssignment": "chief-gpt-oss",
        "compatibilityCheck": "pass",
        "capabilityDiff": [],
        "riskNotes": [],
        "requiresConfirmation": True,
    }
```

- [ ] **Step 4: Run the tests and extend the payload**

Run:

```bash
cd ~/Projects/clay/app/backend
uv run pytest tests/api/test_ai_assignments_api.py -v
```

Expected: PASS. Extend the payload to include provider/model metadata, compatibility notes, and degraded fallback flags aligned with the `E5` spec.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/clay/app
git add backend/src/clay_mc/api backend/tests/api/test_ai_assignments_api.py
git commit -m "feat: add ai assignments review api"
```

### Task 4: Build AI Control Frontend Route And Registry Panels

**Files:**
- Create: `frontend/src/api/ai-client.ts`
- Create: `frontend/src/stores/ai-assignments-store.ts`
- Create: `frontend/src/features/ai-control/ai-control-route.tsx`
- Create: `frontend/src/features/ai-control/components/role-assignment-panel.tsx`
- Create: `frontend/src/features/ai-control/components/model-registry-panel.tsx`
- Create: `frontend/src/features/ai-control/components/provider-status-panel.tsx`
- Create: `frontend/src/features/ai-control/ai-control-route.test.tsx`

- [ ] **Step 1: Write the failing frontend route tests**

```tsx
// ~/Projects/clay/app/frontend/src/features/ai-control/ai-control-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AIControlRoute } from './ai-control-route'

describe('AIControlRoute', () => {
  it('renders assignment, registry, and provider panels', () => {
    render(<AIControlRoute />)

    expect(screen.getByText('Role Assignments')).toBeInTheDocument()
    expect(screen.getByText('Model Registry')).toBeInTheDocument()
    expect(screen.getByText('Provider Status')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd ~/Projects/clay/app/frontend
pnpm test ai-control-route.test.tsx --run
```

Expected: FAIL because the AI control route does not exist yet.

- [ ] **Step 3: Implement the route shell and panels**

```tsx
// ~/Projects/clay/app/frontend/src/features/ai-control/ai-control-route.tsx
export function AIControlRoute() {
  return (
    <main className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(340px,0.9fr)]">
      <section>
        <h2>Role Assignments</h2>
      </section>
      <section>
        <h2>Model Registry</h2>
      </section>
      <section>
        <h2>Provider Status</h2>
      </section>
    </main>
  )
}
```

- [ ] **Step 4: Run the tests and wire bootstrap loading**

Run:

```bash
cd ~/Projects/clay/app/frontend
pnpm test ai-control-route.test.tsx --run
```

Expected: PASS. Then wire `TanStack Query` bootstrap loading from `GET /ai/assignments`, `GET /ai/models`, and `GET /ai/roles`.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/clay/app
git add frontend/src/api frontend/src/stores frontend/src/features/ai-control
git commit -m "feat: add ai control route shell"
```

### Task 5: Implement Conflict Summary, Fallback Banner, And Assignment Review Card

**Files:**
- Create: `backend/src/clay_mc/ai_orchestration/conflicts.py`
- Create: `backend/src/clay_mc/ai_orchestration/fallbacks.py`
- Create: `frontend/src/features/ai-control/components/assignment-review-card.tsx`
- Create: `frontend/src/features/ai-control/components/conflict-summary-panel.tsx`
- Create: `frontend/src/features/ai-control/components/fallback-status-banner.tsx`
- Modify: `frontend/src/features/ai-control/ai-control-route.tsx`
- Create: `backend/tests/ai_orchestration/test_conflict_summary.py`
- Create: `frontend/src/features/ai-control/ai-control-route.test.tsx`

- [ ] **Step 1: Write the failing conflict/fallback tests**

```python
# ~/Projects/clay/app/backend/tests/ai_orchestration/test_conflict_summary.py
from clay_mc.ai_orchestration.conflicts import build_conflict_summary


def test_build_conflict_summary_includes_confidence_penalty() -> None:
    summary = build_conflict_summary(
        roles_involved=["market_scanner", "news_sentiment_agent"],
        conflict_type="market_vs_news",
    )

    assert summary["confidence_penalty"] > 0
```

```tsx
// ~/Projects/clay/app/frontend/src/features/ai-control/ai-control-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AIControlRoute } from './ai-control-route'

describe('AIControlRoute degraded semantics', () => {
  it('renders conflict and fallback sections', () => {
    render(<AIControlRoute />)

    expect(screen.getByText('Conflict Summary')).toBeInTheDocument()
    expect(screen.getByText('Fallback Status')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd ~/Projects/clay/app/backend
uv run pytest tests/ai_orchestration/test_conflict_summary.py -v

cd ~/Projects/clay/app/frontend
pnpm test ai-control-route.test.tsx --run
```

Expected: FAIL because the conflict and fallback layers do not exist yet.

- [ ] **Step 3: Implement conflict and fallback helpers plus UI panels**

```python
# ~/Projects/clay/app/backend/src/clay_mc/ai_orchestration/conflicts.py
def build_conflict_summary(roles_involved: list[str], conflict_type: str) -> dict[str, object]:
    return {
        "conflict_id": "conf-1",
        "roles_involved": roles_involved,
        "conflict_type": conflict_type,
        "summary": "Market structure and external context disagree.",
        "confidence_penalty": 0.18,
        "visibility_level": "warning",
    }
```

```tsx
// ~/Projects/clay/app/frontend/src/features/ai-control/components/conflict-summary-panel.tsx
export function ConflictSummaryPanel() {
  return (
    <section>
      <h2>Conflict Summary</h2>
    </section>
  )
}
```

```tsx
// ~/Projects/clay/app/frontend/src/features/ai-control/components/fallback-status-banner.tsx
export function FallbackStatusBanner() {
  return (
    <section>
      <h2>Fallback Status</h2>
    </section>
  )
}
```

- [ ] **Step 4: Run the tests and add missing-input coverage**

Run:

```bash
cd ~/Projects/clay/app/backend
uv run pytest tests/ai_orchestration/test_conflict_summary.py -v

cd ~/Projects/clay/app/frontend
pnpm test ai-control-route.test.tsx --run
```

Expected: PASS. Then add follow-up coverage showing missing forecast input or fallback-only text mode produces explicit reduced-capability visibility instead of pretending to be full mode.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/clay/app
git add backend/src/clay_mc/ai_orchestration frontend/src/features/ai-control backend/tests/ai_orchestration/test_conflict_summary.py
git commit -m "feat: add ai conflict and fallback surfaces"
```

### Task 6: Add AI Event Stream, Review/Apply Flows, And E2E Coverage

**Files:**
- Create: `backend/src/clay_mc/api/routes/ai_stream.py`
- Create: `backend/src/clay_mc/ai_orchestration/streaming.py`
- Create: `frontend/src/features/ai-control/hooks/use-ai-events-stream.ts`
- Modify: `frontend/src/features/ai-control/ai-control-route.tsx`
- Create: `backend/tests/api/test_ai_stream.py`
- Create: `frontend/tests/e2e/ai-control.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Write the failing stream and review/apply tests**

```python
# ~/Projects/clay/app/backend/tests/api/test_ai_stream.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_ai_stream_returns_event_stream_response() -> None:
    client = TestClient(app)

    response = client.get("/ai/events/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
```

```ts
// ~/Projects/clay/app/frontend/tests/e2e/ai-control.spec.ts
import { expect, test } from '@playwright/test'

test('model assignment change shows review card before apply', async ({ page }) => {
  await page.goto('/ai-control')

  await expect(page.getByText('Role Assignments')).toBeVisible()
  await expect(page.getByText(/review/i)).toBeVisible()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd ~/Projects/clay/app/backend
uv run pytest tests/api/test_ai_stream.py -v

cd ~/Projects/clay/app/frontend
pnpm exec playwright test frontend/tests/e2e/ai-control.spec.ts
```

Expected: FAIL because the stream endpoint and end-to-end review flow are not implemented yet.

- [ ] **Step 3: Implement stream endpoint and review/apply glue**

```python
# ~/Projects/clay/app/backend/src/clay_mc/api/routes/ai_stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/ai/events", tags=["ai-events"])


def event_lines():
    yield "event: assignment_status\n"
    yield 'data: {"roleName":"chief_agent","availabilityStatus":"healthy"}\n\n'


@router.get("/stream")
def get_ai_events_stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream")
```

- [ ] **Step 4: Run the tests and add degraded-switch coverage**

Run:

```bash
cd ~/Projects/clay/app/backend
uv run pytest tests/api/test_ai_stream.py -v

cd ~/Projects/clay/app/frontend
pnpm exec playwright test frontend/tests/e2e/ai-control.spec.ts
```

Expected: PASS. Then add coverage showing degraded fallback switches and manual role changes remain visible to the operator and cannot happen as silent background mutation.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/clay/app
git add backend/src/clay_mc/api/routes/ai_stream.py backend/src/clay_mc/ai_orchestration/streaming.py backend/tests/api/test_ai_stream.py frontend/src/features/ai-control frontend/tests/e2e/ai-control.spec.ts README.md
git commit -m "feat: add ai streaming and review apply flow"
```

## Spec Coverage Check

- Role/provider/model separation is covered by Tasks 1 and 2.
- Registry and assignment validation are covered by Task 2.
- Operator-reviewed assignment flow is covered by Tasks 3 and 6.
- Conflict summaries and degraded fallback visibility are covered by Task 5.
- `HTTP + SSE` interaction expectations are covered by Tasks 3 and 6.
- The plan keeps `Chief Agent` as final synthesis point while avoiding vendor-specific UI contracts.

## Assumptions

- `E1`, `E2`, `E3`, `E4`, and `ADR-005` remain canonical upstream sources.
- Forecast inference stays a separate model class even if some registry metadata is surfaced through the same control UI.
- The current route and file layout are provisional and may be normalized after demo validation without changing the orchestration contracts.

## Execution Handoff

Plan complete and saved to `implementation_plans/e5-ai-roles-orchestration-and-model-assignment-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
