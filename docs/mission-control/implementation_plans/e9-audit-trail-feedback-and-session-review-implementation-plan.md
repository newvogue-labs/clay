> **STATUS: HISTORICAL PLANNING (заморожен).** План относится к этапу планирования (апрель 2026) и сохраняется как исторический контекст.
> Источник истины — `blueprint-v1.md`, `release-gates.md`, ADR (`docs/adr/`) и код (`backend/`).
> Namespace в тексте — планировочный (`clay_mc`, `app/backend`); реальный код использует `clay` / `backend`.

# E9 Audit Trail, Feedback And Session Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working `E9` audit and review layer for `CLAY Mission Control`: structured audit events, signal/session feedback capture, post-session review assembly, AI-assisted review cards, and UI-facing history surfaces without hidden autonomy or opaque log archaeology.

**Architecture:** The implementation extends the provisional `E1` repository with an `audit_review` domain across backend and frontend. Backend services own audit event persistence, feedback submission, session review assembly, and AI review summaries with explicit review-card discipline. Frontend consumes normalized audit/review contracts instead of parsing raw logs. `E9` stays downstream of `E6` signal semantics and `E8` demo outcomes, and upstream of `E10` knowledge/research extensions.

**Tech Stack:** React 19, TypeScript 5.x, Vite, React Router, Zustand, TanStack Query, FastAPI, Pydantic v2, pytest, Vitest, Testing Library, Playwright, Server-Sent Events

---

## Repository Root

This plan assumes the working application repository will live at:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app`

Important:

- this remains a `provisional implementation layout`;
- a later structural refactor is still allowed after demo validation;
- until then, keep audit/review truth in structured backend records, not in screenshot archaeology, vague notes, or heroic grep sessions through random logs.

## File Structure

### Backend

- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/audit.py`
- Create: `backend/src/clay_mc/api/routes/feedback.py`
- Create: `backend/src/clay_mc/api/routes/session_review.py`
- Create: `backend/src/clay_mc/api/routes/review_stream.py`
- Create: `backend/src/clay_mc/audit_review/models.py`
- Create: `backend/src/clay_mc/audit_review/event_log.py`
- Create: `backend/src/clay_mc/audit_review/feedback.py`
- Create: `backend/src/clay_mc/audit_review/session_review.py`
- Create: `backend/src/clay_mc/audit_review/ai_review.py`
- Create: `backend/src/clay_mc/audit_review/service.py`
- Create: `backend/src/clay_mc/audit_review/streaming.py`
- Create: `backend/tests/api/test_audit_api.py`
- Create: `backend/tests/api/test_feedback_api.py`
- Create: `backend/tests/api/test_session_review_api.py`
- Create: `backend/tests/api/test_review_stream.py`
- Create: `backend/tests/audit_review/test_models.py`
- Create: `backend/tests/audit_review/test_event_log.py`
- Create: `backend/tests/audit_review/test_feedback.py`
- Create: `backend/tests/audit_review/test_session_review.py`
- Create: `backend/tests/audit_review/test_ai_review.py`

### Frontend

- Modify: `frontend/src/types/workspace.ts`
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/review/components/audit-event-list.tsx`
- Create: `frontend/src/features/review/components/feedback-card.tsx`
- Create: `frontend/src/features/review/components/session-review-summary.tsx`
- Create: `frontend/src/features/review/components/ai-review-card.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`
- Create: `frontend/src/features/review/review-contracts.test.ts`
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`

### Repo-level

- Modify: `README.md`

---

### Task 1: Establish Audit, Feedback, And Review Contracts

**Files:**
- Create: `backend/src/clay_mc/audit_review/models.py`
- Modify: `frontend/src/types/workspace.ts`
- Create: `backend/tests/audit_review/test_models.py`
- Create: `frontend/src/features/review/review-contracts.test.ts`

- [ ] **Step 1: Write the failing contract tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/audit_review/test_models.py
from clay_mc.audit_review.models import AuditEventRecord


def test_audit_event_record_contains_correlation_and_summary_fields() -> None:
    event = AuditEventRecord.model_validate(
        {
            "event_id": "evt-1",
            "timestamp": "2026-04-15T12:00:00Z",
            "actor": "chief-agent",
            "module": "signals",
            "event_type": "signal_invalidated",
            "object_id": "sig-1",
            "severity": "warning",
            "correlation_id": "session-1",
            "explanation": "Signal invalidated after market structure broke",
            "payload": {"signal_id": "sig-1"},
        }
    )

    assert event.correlation_id == "session-1"
    assert event.event_type == "signal_invalidated"
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/review/review-contracts.test.ts
import { describe, expect, it } from 'vitest'
import type { SessionReviewSummary } from '../../types/workspace'

describe('review contracts', () => {
  it('defines the minimum session review summary shape', () => {
    const summary: SessionReviewSummary = {
      sessionId: 'session-1',
      startedAt: '2026-04-15T10:00:00Z',
      endedAt: '2026-04-15T17:00:00Z',
      primaryFocusPair: 'BTCUSDT',
      strategyUsed: 'Momentum',
      modelAssignmentSnapshot: 'chief:gpt-5.4',
      signalCount: 8,
      executedCount: 3,
      missedCount: 2,
      mismatchCount: 1,
      degradedIncidentCount: 1,
      reviewSummary: 'Session had strong openings but weak discipline after degraded incident.',
    }

    expect(summary.signalCount).toBe(8)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/audit_review/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test review-contracts.test.ts --run
```

Expected: FAIL because `E9` contracts do not exist yet.

- [ ] **Step 3: Implement shared audit/review contracts**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/audit_review/models.py
from pydantic import BaseModel


class AuditEventRecord(BaseModel):
    event_id: str
    timestamp: str
    actor: str
    module: str
    event_type: str
    object_id: str
    severity: str
    correlation_id: str
    explanation: str
    payload: dict[str, object]
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/types/workspace.ts
export interface SessionReviewSummary {
  sessionId: string
  startedAt: string
  endedAt: string
  primaryFocusPair: string
  strategyUsed: string
  modelAssignmentSnapshot: string
  signalCount: number
  executedCount: number
  missedCount: number
  mismatchCount: number
  degradedIncidentCount: number
  reviewSummary: string
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/audit_review/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test review-contracts.test.ts --run
```

Expected: PASS with `E9` contracts available to backend and frontend.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/audit_review frontend/src/types/workspace.ts backend/tests/audit_review frontend/src/features/review/review-contracts.test.ts
git commit -m "feat: add e9 audit and review contracts"
```

### Task 2: Build Audit Event Log And Feedback Logic

**Files:**
- Create: `backend/src/clay_mc/audit_review/event_log.py`
- Create: `backend/src/clay_mc/audit_review/feedback.py`
- Create: `backend/tests/audit_review/test_event_log.py`
- Create: `backend/tests/audit_review/test_feedback.py`

- [ ] **Step 1: Write the failing event-log and feedback tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/audit_review/test_event_log.py
from clay_mc.audit_review.event_log import append_audit_event


def test_append_audit_event_requires_correlation_id_for_session_chain() -> None:
    event = append_audit_event(
        actor="operator",
        module="session",
        event_type="session_started",
        object_id="session-1",
        severity="info",
        correlation_id="session-1",
        explanation="Operator confirmed session start",
        payload={"session_id": "session-1"},
    )

    assert event["correlation_id"] == "session-1"
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/audit_review/test_feedback.py
from clay_mc.audit_review.feedback import build_feedback_record


def test_build_feedback_record_links_feedback_to_signal_and_session() -> None:
    feedback = build_feedback_record(
        signal_id="sig-1",
        session_id="session-1",
        entry_decision="not_entered",
        signal_usefulness="useful",
        trusted_explanation=True,
    )

    assert feedback["signal_id"] == "sig-1"
    assert feedback["session_id"] == "session-1"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/audit_review/test_event_log.py tests/audit_review/test_feedback.py -v
```

Expected: FAIL because event log and feedback helpers do not exist yet.

- [ ] **Step 3: Implement audit event logging and feedback helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/audit_review/event_log.py
def append_audit_event(
    actor: str,
    module: str,
    event_type: str,
    object_id: str,
    severity: str,
    correlation_id: str,
    explanation: str,
    payload: dict[str, object],
) -> dict[str, object]:
    return {
        "event_id": "evt-1",
        "actor": actor,
        "module": module,
        "event_type": event_type,
        "object_id": object_id,
        "severity": severity,
        "correlation_id": correlation_id,
        "explanation": explanation,
        "payload": payload,
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/audit_review/feedback.py
def build_feedback_record(
    signal_id: str,
    session_id: str,
    entry_decision: str,
    signal_usefulness: str,
    trusted_explanation: bool,
) -> dict[str, object]:
    return {
        "feedback_id": "feedback-1",
        "signal_id": signal_id,
        "session_id": session_id,
        "entry_decision": entry_decision,
        "signal_usefulness": signal_usefulness,
        "trusted_explanation": trusted_explanation,
    }
```

- [ ] **Step 4: Run the tests and add orphaned-feedback coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/audit_review/test_event_log.py tests/audit_review/test_feedback.py -v
```

Expected: PASS. Then add coverage proving orphaned feedback without signal/session linkage is rejected or marked unresolved.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/audit_review backend/tests/audit_review/test_event_log.py backend/tests/audit_review/test_feedback.py
git commit -m "feat: add e9 audit event log and feedback"
```

### Task 3: Build Session Review And AI Review Assembly

**Files:**
- Create: `backend/src/clay_mc/audit_review/session_review.py`
- Create: `backend/src/clay_mc/audit_review/ai_review.py`
- Create: `backend/tests/audit_review/test_session_review.py`
- Create: `backend/tests/audit_review/test_ai_review.py`

- [ ] **Step 1: Write the failing review assembly tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/audit_review/test_session_review.py
from clay_mc.audit_review.session_review import build_session_review_summary


def test_build_session_review_summary_combines_outcomes_incidents_and_feedback() -> None:
    summary = build_session_review_summary(
        session_id="session-1",
        signal_count=8,
        executed_count=3,
        missed_count=2,
        mismatch_count=1,
        degraded_incident_count=1,
    )

    assert summary["session_id"] == "session-1"
    assert summary["degraded_incident_count"] == 1
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/audit_review/test_ai_review.py
from clay_mc.audit_review.ai_review import build_ai_review_card


def test_build_ai_review_card_requires_confirmation_for_followups() -> None:
    card = build_ai_review_card(
        session_id="session-1",
        summary="Late entries increased after degraded recovery.",
        strengths=["Good discipline before incident"],
        weaknesses=["Resume handling too aggressive"],
        proposed_followups=["Review pause-resume checklist"],
    )

    assert card["requires_confirmation"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/audit_review/test_session_review.py tests/audit_review/test_ai_review.py -v
```

Expected: FAIL because review assembly and AI review helpers do not exist yet.

- [ ] **Step 3: Implement review assembly and AI review helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/audit_review/session_review.py
def build_session_review_summary(
    session_id: str,
    signal_count: int,
    executed_count: int,
    missed_count: int,
    mismatch_count: int,
    degraded_incident_count: int,
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "signal_count": signal_count,
        "executed_count": executed_count,
        "missed_count": missed_count,
        "mismatch_count": mismatch_count,
        "degraded_incident_count": degraded_incident_count,
        "review_summary": "Session review assembled",
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/audit_review/ai_review.py
def build_ai_review_card(
    session_id: str,
    summary: str,
    strengths: list[str],
    weaknesses: list[str],
    proposed_followups: list[str],
) -> dict[str, object]:
    return {
        "suggestion_id": "review-card-1",
        "session_id": session_id,
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "proposed_followups": proposed_followups,
        "requires_confirmation": True,
    }
```

- [ ] **Step 4: Run the tests and add raw-evidence visibility coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/audit_review/test_session_review.py tests/audit_review/test_ai_review.py -v
```

Expected: PASS. Then add coverage proving AI summaries do not replace raw review evidence and remain additive.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/audit_review backend/tests/audit_review/test_session_review.py backend/tests/audit_review/test_ai_review.py
git commit -m "feat: add e9 session review assembly"
```

### Task 4: Build Audit, Feedback, And Session Review APIs Plus Streams

**Files:**
- Create: `backend/src/clay_mc/api/routes/audit.py`
- Create: `backend/src/clay_mc/api/routes/feedback.py`
- Create: `backend/src/clay_mc/api/routes/session_review.py`
- Create: `backend/src/clay_mc/api/routes/review_stream.py`
- Create: `backend/src/clay_mc/audit_review/service.py`
- Create: `backend/src/clay_mc/audit_review/streaming.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/api/test_audit_api.py`
- Create: `backend/tests/api/test_feedback_api.py`
- Create: `backend/tests/api/test_session_review_api.py`
- Create: `backend/tests/api/test_review_stream.py`

- [ ] **Step 1: Write the failing API and stream tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_audit_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_audit_events_endpoint_returns_structured_items() -> None:
    client = TestClient(app)

    response = client.get("/audit/events")

    assert response.status_code == 200
    assert len(response.json()["items"]) > 0
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_review_stream.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_review_stream_returns_event_stream_response() -> None:
    client = TestClient(app)

    response = client.get("/audit/events/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_audit_api.py tests/api/test_feedback_api.py tests/api/test_session_review_api.py tests/api/test_review_stream.py -v
```

Expected: FAIL because the `E9` routes and review stream do not exist yet.

- [ ] **Step 3: Implement routes and streaming**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/audit.py
from fastapi import APIRouter


router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events")
def get_audit_events() -> dict[str, object]:
    return {
        "items": [
            {
                "event_id": "evt-1",
                "timestamp": "2026-04-15T12:00:00Z",
                "event_type": "signal_invalidated",
                "actor": "chief-agent",
                "module": "signals",
                "severity": "warning",
                "correlation_id": "session-1",
                "summary": "Signal invalidated after structure break",
            }
        ]
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/review_stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/audit", tags=["review-stream"])


def event_lines():
    yield "event: audit_event_added\n"
    yield 'data: {"eventId":"evt-1","eventType":"feedback_submitted","severity":"info"}\n\n'


@router.get("/events/stream")
def get_audit_events_stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream")
```

- [ ] **Step 4: Run the tests and add session-review coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_audit_api.py tests/api/test_feedback_api.py tests/api/test_session_review_api.py tests/api/test_review_stream.py -v
```

Expected: PASS. Then extend coverage for `POST /signals/{signalId}/feedback`, `GET /session-review/{sessionId}`, and AI review acknowledgement endpoints.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api backend/src/clay_mc/audit_review backend/tests/api/test_audit_api.py backend/tests/api/test_feedback_api.py backend/tests/api/test_session_review_api.py backend/tests/api/test_review_stream.py
git commit -m "feat: add e9 audit and review apis"
```

### Task 5: Wire Audit And Review Surfaces Into Workspace UI

**Files:**
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/review/components/audit-event-list.tsx`
- Create: `frontend/src/features/review/components/feedback-card.tsx`
- Create: `frontend/src/features/review/components/session-review-summary.tsx`
- Create: `frontend/src/features/review/components/ai-review-card.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`

- [ ] **Step 1: Write the failing workspace rendering tests**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/trading-workspace-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TradingWorkspaceRoute } from './trading-workspace-route'

describe('TradingWorkspaceRoute E9 integrations', () => {
  it('renders audit, feedback, and review surfaces', () => {
    render(<TradingWorkspaceRoute />)

    expect(screen.getByText(/Audit Trail/i)).toBeInTheDocument()
    expect(screen.getByText(/Feedback/i)).toBeInTheDocument()
    expect(screen.getByText(/Session Review/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: FAIL because the workspace has not been wired to `E9` review surfaces yet.

- [ ] **Step 3: Implement `E9`-aware review components**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/review/components/audit-event-list.tsx
export function AuditEventList() {
  return (
    <section>
      <h2>Audit Trail</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/review/components/feedback-card.tsx
export function FeedbackCard() {
  return (
    <section>
      <h2>Feedback</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/review/components/session-review-summary.tsx
export function SessionReviewSummaryCard() {
  return (
    <section>
      <h2>Session Review</h2>
    </section>
  )
}
```

- [ ] **Step 4: Run the tests and add degraded-history coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: PASS. Then add UI coverage proving degraded incidents, mismatches, and AI review cards remain visible and do not collapse into a single generic summary.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/features/review frontend/src/features/workspace frontend/src/api/workspace-client.ts frontend/src/stores/workspace-store.ts
git commit -m "feat: wire e9 audit review into workspace"
```

### Task 6: Add End-To-End Coverage For Review And Feedback Flow

**Files:**
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Write the failing end-to-end tests**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/tests/e2e/trading-workspace.spec.ts
import { expect, test } from '@playwright/test'

test('degraded incident remains visible in session review', async ({ page }) => {
  await page.goto('/trading')

  await expect(page.getByText(/degraded/i)).toBeVisible()
  await expect(page.getByText(/Session Review/i)).toBeVisible()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: FAIL because end-to-end `E9` rendering is not complete yet.

- [ ] **Step 3: Implement the missing state hooks and docs updates**

```md
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/README.md
## E9 Audit And Session Review

- `GET /audit/events` returns structured audit events
- `GET /session-review/{sessionId}` returns normalized session review
- `POST /signals/{signalId}/feedback` captures operator feedback
- `GET /audit/events/stream` pushes new audit events

AI review summaries are additive. They do not replace raw session evidence or silently change strategy.
```

- [ ] **Step 4: Run the tests and add orphaned-feedback coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: PASS. Then add end-to-end coverage for feedback submit flows, review filters, and AI review cards that require confirmation.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/tests/e2e/trading-workspace.spec.ts README.md
git commit -m "feat: finalize e9 review coverage"
```

## Spec Coverage Check

- Audit event, feedback, session review, and AI review contracts are covered by Tasks 1 and 5.
- Structured audit logging and feedback linkage are covered by Task 2.
- Session review synthesis and AI review-card discipline are covered by Task 3.
- `HTTP + SSE` routes for audit events, feedback, and session review are covered by Task 4.
- Workspace visibility for audit, feedback, incidents, and AI review cards is covered by Tasks 5 and 6.

## Assumptions

- `E6` and `E8` remain the canonical upstream sources for signal semantics and demo evidence.
- AI review in `E9` remains assistive and operator-reviewed, never silently mutating runtime strategy.
- The route and file structure remain provisional until later demo-stage cleanup.

## Execution Handoff

Plan complete and saved to `implementation_plans/e9-audit-trail-feedback-and-session-review-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
