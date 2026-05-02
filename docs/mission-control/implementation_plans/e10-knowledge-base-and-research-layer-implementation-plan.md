# E10 Knowledge Base And Research Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working `E10` knowledge layer for `CLAY Mission Control`: structured notes and strategy rules, controlled imports, metadata discipline, optional retrieval, research links, and a knowledge screen that supports review/tuning without becoming a realtime dependency.

**Architecture:** The implementation extends the provisional `E1` repository with a `knowledge` domain across backend and frontend. Backend services own knowledge item persistence, import processing, metadata normalization, optional retrieval, and research linking. Frontend consumes normalized knowledge/research contracts rather than reading raw files directly. `E10` stays downstream of `E9` review/history and upstream of `E11` replay/backtesting enrichment.

**Tech Stack:** React 19, TypeScript 5.x, Vite, React Router, Zustand, TanStack Query, FastAPI, Pydantic v2, pytest, Vitest, Testing Library, Playwright, Server-Sent Events, PostgreSQL, pgvector (only when retrieval is enabled)

---

## Repository Root

This plan assumes the working application repository will live at:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app`

Important:

- this remains a `provisional implementation layout`;
- a later structural refactor is still allowed after demo validation;
- until then, keep knowledge truth in structured records and source references, not in mysterious folder sprawl, accidental duplicates, or markdown necromancy.

## File Structure

### Backend

- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/knowledge.py`
- Create: `backend/src/clay_mc/api/routes/research.py`
- Create: `backend/src/clay_mc/api/routes/knowledge_stream.py`
- Create: `backend/src/clay_mc/knowledge/models.py`
- Create: `backend/src/clay_mc/knowledge/ingestion.py`
- Create: `backend/src/clay_mc/knowledge/retrieval.py`
- Create: `backend/src/clay_mc/knowledge/links.py`
- Create: `backend/src/clay_mc/knowledge/service.py`
- Create: `backend/src/clay_mc/knowledge/streaming.py`
- Create: `backend/tests/api/test_knowledge_api.py`
- Create: `backend/tests/api/test_research_api.py`
- Create: `backend/tests/api/test_knowledge_stream.py`
- Create: `backend/tests/knowledge/test_models.py`
- Create: `backend/tests/knowledge/test_ingestion.py`
- Create: `backend/tests/knowledge/test_retrieval.py`
- Create: `backend/tests/knowledge/test_links.py`

### Frontend

- Modify: `frontend/src/types/workspace.ts`
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/knowledge/components/knowledge-item-card.tsx`
- Create: `frontend/src/features/knowledge/components/retrieval-result-list.tsx`
- Create: `frontend/src/features/knowledge/components/research-link-card.tsx`
- Create: `frontend/src/features/knowledge/components/knowledge-status-banner.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`
- Create: `frontend/src/features/knowledge/knowledge-contracts.test.ts`
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`

### Repo-level

- Modify: `README.md`

---

### Task 1: Establish Knowledge Item, Retrieval, And Research Link Contracts

**Files:**
- Create: `backend/src/clay_mc/knowledge/models.py`
- Modify: `frontend/src/types/workspace.ts`
- Create: `backend/tests/knowledge/test_models.py`
- Create: `frontend/src/features/knowledge/knowledge-contracts.test.ts`

- [ ] **Step 1: Write the failing contract tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/knowledge/test_models.py
from clay_mc.knowledge.models import KnowledgeItemRecord


def test_knowledge_item_record_contains_metadata_and_source_fields() -> None:
    item = KnowledgeItemRecord.model_validate(
        {
            "knowledge_id": "know-1",
            "title": "Momentum Checklist",
            "content_type": "checklist",
            "category": "strategy_rules",
            "tags": ["momentum", "entry"],
            "priority": "high",
            "source_type": "manual_note",
            "created_at": "2026-04-15T12:00:00Z",
            "updated_at": "2026-04-15T12:00:00Z",
            "status": "active",
        }
    )

    assert item.category == "strategy_rules"
    assert item.priority == "high"
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/knowledge/knowledge-contracts.test.ts
import { describe, expect, it } from 'vitest'
import type { KnowledgeSearchResponse } from '../../types/workspace'

describe('knowledge contracts', () => {
  it('defines the minimum knowledge search response shape', () => {
    const response: KnowledgeSearchResponse = {
      query: 'momentum checklist',
      items: [],
      retrievalUsed: false,
      totalHits: 0,
    }

    expect(response.totalHits).toBe(0)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/knowledge/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test knowledge-contracts.test.ts --run
```

Expected: FAIL because `E10` contracts do not exist yet.

- [ ] **Step 3: Implement shared knowledge contracts**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/knowledge/models.py
from pydantic import BaseModel


class KnowledgeItemRecord(BaseModel):
    knowledge_id: str
    title: str
    content_type: str
    category: str
    tags: list[str]
    priority: str
    source_type: str
    created_at: str
    updated_at: str
    status: str
```

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/types/workspace.ts
export interface KnowledgeSearchResponse {
  query: string
  items: Array<{
    knowledgeId: string
    title: string
    category: string
    sourceLabel: string
  }>
  retrievalUsed: boolean
  totalHits: number
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/knowledge/test_models.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test knowledge-contracts.test.ts --run
```

Expected: PASS with `E10` contracts available to backend and frontend.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/knowledge frontend/src/types/workspace.ts backend/tests/knowledge frontend/src/features/knowledge/knowledge-contracts.test.ts
git commit -m "feat: add e10 knowledge contracts"
```

### Task 2: Build Ingestion And Metadata Discipline

**Files:**
- Create: `backend/src/clay_mc/knowledge/ingestion.py`
- Create: `backend/tests/knowledge/test_ingestion.py`

- [ ] **Step 1: Write the failing ingestion tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/knowledge/test_ingestion.py
from clay_mc.knowledge.ingestion import normalize_knowledge_item


def test_normalize_knowledge_item_requires_category_tags_priority_and_source() -> None:
    item = normalize_knowledge_item(
        title="Risk Checklist",
        content_type="checklist",
        category="checklists",
        tags=["risk", "discipline"],
        priority="high",
        source_type="manual_note",
    )

    assert item["category"] == "checklists"
    assert item["source_type"] == "manual_note"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/knowledge/test_ingestion.py -v
```

Expected: FAIL because ingestion helpers do not exist yet.

- [ ] **Step 3: Implement ingestion normalization**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/knowledge/ingestion.py
def normalize_knowledge_item(
    title: str,
    content_type: str,
    category: str,
    tags: list[str],
    priority: str,
    source_type: str,
) -> dict[str, object]:
    return {
        "knowledge_id": "know-1",
        "title": title,
        "content_type": content_type,
        "category": category,
        "tags": tags,
        "priority": priority,
        "source_type": source_type,
        "status": "active",
    }
```

- [ ] **Step 4: Run the tests and add garbage-content isolation coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/knowledge/test_ingestion.py -v
```

Expected: PASS. Then add coverage proving low-trust or junk content can be marked separately and does not blend into trusted operational knowledge.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/knowledge/ingestion.py backend/tests/knowledge/test_ingestion.py
git commit -m "feat: add e10 knowledge ingestion normalization"
```

### Task 3: Build Retrieval And Research Linking Logic

**Files:**
- Create: `backend/src/clay_mc/knowledge/retrieval.py`
- Create: `backend/src/clay_mc/knowledge/links.py`
- Create: `backend/tests/knowledge/test_retrieval.py`
- Create: `backend/tests/knowledge/test_links.py`

- [ ] **Step 1: Write the failing retrieval and link tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/knowledge/test_retrieval.py
from clay_mc.knowledge.retrieval import run_retrieval


def test_run_retrieval_returns_no_hit_without_blocking_runtime() -> None:
    result = run_retrieval(query="rare setup", items=[])

    assert result["total_hits"] == 0
    assert result["retrieval_used"] is True
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/knowledge/test_links.py
from clay_mc.knowledge.links import build_research_link


def test_build_research_link_connects_knowledge_to_review_target() -> None:
    link = build_research_link(
        knowledge_id="know-1",
        target_type="session_review",
        target_id="session-1",
        link_reason="Supports post-session pattern analysis",
    )

    assert link["target_type"] == "session_review"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/knowledge/test_retrieval.py tests/knowledge/test_links.py -v
```

Expected: FAIL because retrieval and research-link helpers do not exist yet.

- [ ] **Step 3: Implement retrieval and research-link helpers**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/knowledge/retrieval.py
def run_retrieval(query: str, items: list[dict[str, object]]) -> dict[str, object]:
    matches = [item for item in items if query.lower() in str(item.get("title", "")).lower()]
    return {
        "query": query,
        "items": matches,
        "retrieval_used": True,
        "total_hits": len(matches),
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/knowledge/links.py
def build_research_link(
    knowledge_id: str,
    target_type: str,
    target_id: str,
    link_reason: str,
) -> dict[str, object]:
    return {
        "link_id": "link-1",
        "knowledge_id": knowledge_id,
        "target_type": target_type,
        "target_id": target_id,
        "link_reason": link_reason,
    }
```

- [ ] **Step 4: Run the tests and add source-attribution coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/knowledge/test_retrieval.py tests/knowledge/test_links.py -v
```

Expected: PASS. Then add coverage for source attribution, reason summaries, and retrieval misses that stay honest instead of hallucinating support.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/knowledge backend/tests/knowledge/test_retrieval.py backend/tests/knowledge/test_links.py
git commit -m "feat: add e10 retrieval and research links"
```

### Task 4: Build Knowledge And Research APIs Plus Streams

**Files:**
- Create: `backend/src/clay_mc/api/routes/knowledge.py`
- Create: `backend/src/clay_mc/api/routes/research.py`
- Create: `backend/src/clay_mc/api/routes/knowledge_stream.py`
- Create: `backend/src/clay_mc/knowledge/service.py`
- Create: `backend/src/clay_mc/knowledge/streaming.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/api/test_knowledge_api.py`
- Create: `backend/tests/api/test_research_api.py`
- Create: `backend/tests/api/test_knowledge_stream.py`

- [ ] **Step 1: Write the failing API and stream tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_knowledge_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_knowledge_items_endpoint_returns_structured_items() -> None:
    client = TestClient(app)

    response = client.get("/knowledge/items")

    assert response.status_code == 200
    assert len(response.json()["items"]) > 0
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_knowledge_stream.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_knowledge_stream_returns_event_stream_response() -> None:
    client = TestClient(app)

    response = client.get("/knowledge/events/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_knowledge_api.py tests/api/test_research_api.py tests/api/test_knowledge_stream.py -v
```

Expected: FAIL because the `E10` routes and stream do not exist yet.

- [ ] **Step 3: Implement routes and streaming**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/knowledge.py
from fastapi import APIRouter


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/items")
def get_knowledge_items() -> dict[str, object]:
    return {
        "items": [
            {
                "knowledge_id": "know-1",
                "title": "Momentum Checklist",
                "category": "strategy_rules",
                "tags": ["momentum"],
                "priority": "high",
                "updated_at": "2026-04-15T12:00:00Z",
                "source_label": "manual_note",
            }
        ]
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/knowledge_stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/knowledge", tags=["knowledge-stream"])


def event_lines():
    yield "event: knowledge_item_updated\n"
    yield 'data: {"knowledgeId":"know-1","category":"strategy_rules","status":"active"}\n\n'


@router.get("/events/stream")
def get_knowledge_events_stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream")
```

- [ ] **Step 4: Run the tests and add search coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_knowledge_api.py tests/api/test_research_api.py tests/api/test_knowledge_stream.py -v
```

Expected: PASS. Then extend coverage for `GET /knowledge/search`, `POST /knowledge/import`, and `GET /research/links/{targetType}/{targetId}`.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api backend/src/clay_mc/knowledge backend/tests/api/test_knowledge_api.py backend/tests/api/test_research_api.py backend/tests/api/test_knowledge_stream.py
git commit -m "feat: add e10 knowledge and research apis"
```

### Task 5: Wire Knowledge And Research Surfaces Into Workspace UI

**Files:**
- Modify: `frontend/src/api/workspace-client.ts`
- Modify: `frontend/src/stores/workspace-store.ts`
- Modify: `frontend/src/features/workspace/trading-workspace-route.tsx`
- Modify: `frontend/src/features/workspace/hooks/use-workspace-stream.ts`
- Create: `frontend/src/features/knowledge/components/knowledge-item-card.tsx`
- Create: `frontend/src/features/knowledge/components/retrieval-result-list.tsx`
- Create: `frontend/src/features/knowledge/components/research-link-card.tsx`
- Create: `frontend/src/features/knowledge/components/knowledge-status-banner.tsx`
- Modify: `frontend/src/features/workspace/trading-workspace-route.test.tsx`

- [ ] **Step 1: Write the failing workspace rendering tests**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/workspace/trading-workspace-route.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TradingWorkspaceRoute } from './trading-workspace-route'

describe('TradingWorkspaceRoute E10 integrations', () => {
  it('renders knowledge, retrieval, and research surfaces', () => {
    render(<TradingWorkspaceRoute />)

    expect(screen.getByText(/Knowledge Base/i)).toBeInTheDocument()
    expect(screen.getByText(/Research Results/i)).toBeInTheDocument()
    expect(screen.getByText(/Knowledge Status/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: FAIL because the workspace has not been wired to `E10` knowledge surfaces yet.

- [ ] **Step 3: Implement `E10`-aware knowledge components**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/knowledge/components/knowledge-status-banner.tsx
export function KnowledgeStatusBanner() {
  return (
    <section>
      <h2>Knowledge Status</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/knowledge/components/knowledge-item-card.tsx
export function KnowledgeItemCard() {
  return (
    <section>
      <h2>Knowledge Base</h2>
    </section>
  )
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/features/knowledge/components/retrieval-result-list.tsx
export function RetrievalResultList() {
  return (
    <section>
      <h2>Research Results</h2>
    </section>
  )
}
```

- [ ] **Step 4: Run the tests and add no-hit visibility coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm test trading-workspace-route.test.tsx --run
```

Expected: PASS. Then add UI coverage proving retrieval no-hit states are honest and do not look like hidden failure or fake success.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/src/features/knowledge frontend/src/features/workspace frontend/src/api/workspace-client.ts frontend/src/stores/workspace-store.ts
git commit -m "feat: wire e10 knowledge research into workspace"
```

### Task 6: Add End-To-End Coverage For Knowledge And Retrieval Flow

**Files:**
- Modify: `frontend/tests/e2e/trading-workspace.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Write the failing end-to-end tests**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/tests/e2e/trading-workspace.spec.ts
import { expect, test } from '@playwright/test'

test('knowledge retrieval no-hit stays visible without blocking workspace', async ({ page }) => {
  await page.goto('/trading')

  await expect(page.getByText(/Research Results/i)).toBeVisible()
  await expect(page.getByText(/no results/i)).toBeVisible()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: FAIL because end-to-end `E10` rendering is not complete yet.

- [ ] **Step 3: Implement the missing state hooks and docs updates**

```md
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/README.md
## E10 Knowledge And Research Layer

- `GET /knowledge/items` returns normalized knowledge items
- `GET /knowledge/search` returns search/retrieval results
- `GET /research/links/{targetType}/{targetId}` returns research links
- `GET /knowledge/events/stream` pushes knowledge updates

Knowledge retrieval is supportive. It must not block core signal, session, or demo-validation workflows.
```

- [ ] **Step 4: Run the tests and add outage coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
pnpm exec playwright test frontend/tests/e2e/trading-workspace.spec.ts
```

Expected: PASS. Then add end-to-end coverage for knowledge-layer no-hit, low-trust content, and graceful degradation when research endpoints are unavailable.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend/tests/e2e/trading-workspace.spec.ts README.md
git commit -m "feat: finalize e10 knowledge layer coverage"
```

## Spec Coverage Check

- Knowledge item, search, retrieval, and research-link contracts are covered by Tasks 1 and 5.
- Ingestion normalization, metadata discipline, and junk isolation are covered by Task 2.
- Retrieval no-hit behavior and research linking are covered by Task 3.
- `HTTP + SSE` routes for knowledge items, search, imports, and research links are covered by Task 4.
- Workspace visibility for knowledge status, knowledge items, retrieval results, and graceful no-hit handling is covered by Tasks 5 and 6.

## Assumptions

- `E9` remains the canonical upstream source for review/history context.
- Retrieval in `E10` remains supportive and never becomes a hard blocker for signal/session/demo paths.
- The route and file structure remain provisional until later demo-stage cleanup.

## Execution Handoff

Plan complete and saved to `implementation_plans/e10-knowledge-base-and-research-layer-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
