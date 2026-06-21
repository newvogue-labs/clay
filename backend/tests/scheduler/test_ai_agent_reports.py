"""Tests for subagent report injection into chief context (5c.5.1).

Coverage:
1. ``OpsRepository.list_latest_agent_runs`` — dedup, error/content filtering.
2. ``_render_context`` with session — subagent_reports section shape.
3. Content cap at 2000 chars.
4. Regression: non-chief roles byte-identical with/without session.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from clay.ai_control.models import (
    AIControlSnapshot,
    AIControlSummary,
    AssignmentSnapshot,
    FallbackSnapshot,
    RoleDefinitionSnapshot,
)
from clay.db.models_ops import AIAgentRun
from clay.db.repositories_ops import OpsRepository
from clay.scheduler.ai_agent_job import _render_context

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_ROLE_IDS = ["market-scanner", "news-sentiment-agent", "forecast-model", "chief-agent"]


def _snapshot_with_roles(role_ids: list[str] | None = None) -> AIControlSnapshot:
    if role_ids is None:
        role_ids = _ROLE_IDS
    roles = [
        RoleDefinitionSnapshot(
            role_id=rid,
            role_name=rid.replace("-", " ").title(),
            responsibility="test",
            inputs=["x"],
            outputs=["y"],
            allowed_actions=["scan"],
            constraints=["none"],
        )
        for rid in role_ids
    ]
    return AIControlSnapshot(
        summary=AIControlSummary(
            overall_status="healthy",
            chief_agent_model="gemma4:e2b-it-qat",
            active_conflict_count=0,
            degraded_role_count=0,
            fallback_active=False,
            last_reviewed_at=None,
        ),
        roles=roles,
        models=[],
        assignments=[
            AssignmentSnapshot(
                role_id=rid,
                role_name=rid.replace("-", " ").title(),
                model_id="gemini-3.1-flash-lite",
                model_display_name="Flash Lite",
                provider="Google (AI Studio)",
                assignment_mode="active",
                assignment_health="healthy",
                confidence_penalty=0.0,
                review_required=False,
                reason="ok",
            )
            for rid in role_ids
        ],
        conflicts=[],
        fallback=FallbackSnapshot(
            fallback_active=False,
            local_fallback_ready=True,
            degraded_roles=[],
            operator_message="All systems nominal",
        ),
        pending_review=None,
    )


def _insert_run(
    session: Any,
    role_id: str,
    content: str,
    *,
    created_at: datetime | None = None,
    error: str | None = None,
) -> AIAgentRun:
    run = AIAgentRun(
        created_at=created_at or datetime.now(UTC),
        role_id=role_id,
        model_id="gemini-3.1-flash-lite",
        content=content,
        thinking=None,
        error=error,
    )
    session.add(run)
    session.flush()
    return run


# ===================================================================
# list_latest_agent_runs
# ===================================================================


class TestListLatestAgentRuns:
    def test_multiple_rows_per_role_returns_latest(self, db_session: Any) -> None:
        repo = OpsRepository(db_session)
        now = datetime.now(UTC)
        _insert_run(db_session, "market-scanner", "old", created_at=now - timedelta(minutes=10))
        _insert_run(db_session, "market-scanner", "latest", created_at=now)
        result = repo.list_latest_agent_runs(["market-scanner"])
        assert result["market-scanner"].content == "latest"

    def test_error_rows_ignored(self, db_session: Any) -> None:
        repo = OpsRepository(db_session)
        now = datetime.now(UTC)
        _insert_run(db_session, "market-scanner", "good", created_at=now - timedelta(minutes=5))
        _insert_run(db_session, "market-scanner", "bad", created_at=now, error="boom")
        result = repo.list_latest_agent_runs(["market-scanner"])
        assert result["market-scanner"].content == "good"

    def test_empty_content_ignored(self, db_session: Any) -> None:
        repo = OpsRepository(db_session)
        now = datetime.now(UTC)
        _insert_run(db_session, "market-scanner", "", created_at=now)
        _insert_run(db_session, "market-scanner", "real", created_at=now - timedelta(minutes=1))
        result = repo.list_latest_agent_runs(["market-scanner"])
        assert result["market-scanner"].content == "real"

    def test_role_without_rows_absent(self, db_session: Any) -> None:
        repo = OpsRepository(db_session)
        _insert_run(db_session, "market-scanner", "hello")
        result = repo.list_latest_agent_runs(["market-scanner", "news-sentiment-agent"])
        assert "market-scanner" in result
        assert "news-sentiment-agent" not in result

    def test_empty_role_ids_returns_empty(self, db_session: Any) -> None:
        repo = OpsRepository(db_session)
        assert repo.list_latest_agent_runs([]) == {}


# ===================================================================
# _render_context with subagent_reports
# ===================================================================


class TestRenderContextWithReports:
    def test_three_reports_all_present(self, db_session: Any) -> None:
        now = datetime.now(UTC)
        _insert_run(db_session, "market-scanner", "scanner output", created_at=now - timedelta(minutes=5))
        _insert_run(db_session, "news-sentiment-agent", "news output", created_at=now - timedelta(minutes=3))
        _insert_run(db_session, "forecast-model", "forecast output", created_at=now - timedelta(minutes=1))
        snap = _snapshot_with_roles()
        ctx = _render_context(snap, "chief-agent", session=db_session)
        assert "=== subagent_reports ===" in ctx
        assert "[market-scanner]" in ctx
        assert "[news-sentiment-agent]" in ctx
        assert "[forecast-model]" in ctx
        assert "scanner output" in ctx
        assert "news output" in ctx
        assert "forecast output" in ctx
        assert "no recent reports" not in ctx

    def test_one_report_only(self, db_session: Any) -> None:
        _insert_run(db_session, "forecast-model", "only forecast content")
        snap = _snapshot_with_roles()
        ctx = _render_context(snap, "chief-agent", session=db_session)
        assert "[forecast-model]" in ctx
        assert "only forecast content" in ctx
        assert "[market-scanner]" not in ctx

    def test_no_reports(self, db_session: Any) -> None:
        snap = _snapshot_with_roles()
        ctx = _render_context(snap, "chief-agent", session=db_session)
        assert "=== subagent_reports ===" in ctx
        assert "no recent reports" in ctx

    def test_no_reports_roles_without_data(self, db_session: Any) -> None:
        _insert_run(db_session, "market-scanner", "hello", error="boom")
        snap = _snapshot_with_roles()
        ctx = _render_context(snap, "chief-agent", session=db_session)
        assert "no recent reports" in ctx

    def test_content_cap_2000(self, db_session: Any) -> None:
        long_content = "a" * 2500
        _insert_run(db_session, "market-scanner", long_content)
        snap = _snapshot_with_roles()
        ctx = _render_context(snap, "chief-agent", session=db_session)
        assert "[market-scanner]" in ctx
        assert "a" * 2000 in ctx
        assert "...[truncated]" in ctx
        assert "a" * 2001 not in ctx

    def test_age_in_minutes(self, db_session: Any) -> None:
        now = datetime.now(UTC)
        _insert_run(db_session, "forecast-model", "fresh", created_at=now - timedelta(minutes=7))
        snap = _snapshot_with_roles()
        ctx = _render_context(snap, "chief-agent", session=db_session)
        assert "(7 min ago):" in ctx

    def test_age_zero_minutes(self, db_session: Any) -> None:
        _insert_run(db_session, "forecast-model", "just now")
        snap = _snapshot_with_roles()
        ctx = _render_context(snap, "chief-agent", session=db_session)
        assert "(0 min ago):" in ctx


# ===================================================================
# regression: non-chief roles byte-identical
# ===================================================================


class TestRenderContextNonChiefRegression:
    def test_non_chief_byte_identical_without_session(self, db_session: Any) -> None:
        snap = _snapshot_with_roles()
        ctx_no_session = _render_context(snap, "market-scanner")
        ctx_with_session = _render_context(snap, "market-scanner", session=db_session)
        assert ctx_no_session == ctx_with_session

    def test_non_chief_byte_identical_none_session(self, db_session: Any) -> None:
        snap = _snapshot_with_roles()
        ctx_none = _render_context(snap, "market-scanner")
        ctx_explicit = _render_context(snap, "market-scanner", session=None)
        assert ctx_none == ctx_explicit
