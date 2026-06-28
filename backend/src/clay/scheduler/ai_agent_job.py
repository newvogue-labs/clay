"""AIAgentCycleJob — scheduler-driven agent-run for AI-control review.

DEPLOY-5 / 5b-ii.2b-ii: periodic async job that:

1. Takes a ``build_snapshot(session)`` of the AI-control service state.
2. Renders 7 plain-text sections from the snapshot (stable prompt shape).
3. Calls ``AgentRunner.run_agent(role_id, context)`` (fail-loud).
4. Persists the result (content/thinking/error) to ``ops.ai_agent_runs``.

Flag-gated by ``SchedulerSettings.ai_agent_enabled`` (default ``False``).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging

from sqlalchemy.orm import Session, sessionmaker

from clay.ai_control.models import AIControlSnapshot
from clay.ai_control.runner import AgentRunner, ModelUnavailableError
from clay.ai_control.service import AIControlService
from clay.db.models_ops import AIAgentRun
from clay.db.repositories_ops import OpsRepository

logger = logging.getLogger(__name__)


def _render_context(
    snapshot: AIControlSnapshot,
    role_id: str | None = None,
    session: Session | None = None,
) -> str:
    """Deterministic plain-text rendering of the 7 AIControlSnapshot sections.

    Every section is always present (empty → ``none``) for prompt stability.
    When ``role_id == "chief-agent"`` and ``session`` is provided, appends a
    ``=== subagent_reports ===`` section with the latest outputs from every
    subagent role (5c.5).
    """

    def _maybe_list(items: list[object]) -> str:
        return "\n".join(str(i) for i in items) if items else "none"

    lines: list[str] = []

    lines.append("=== summary ===")
    s = snapshot.summary
    lines.append(
        f"overall_status={s.overall_status} "
        f"chief_agent_model={s.chief_agent_model} "
        f"active_conflict_count={s.active_conflict_count} "
        f"degraded_role_count={s.degraded_role_count} "
        f"fallback_active={s.fallback_active} "
        f"last_reviewed_at={s.last_reviewed_at}"
    )

    lines.append("")
    lines.append("=== roles ===")
    if snapshot.roles:
        for r in snapshot.roles:
            lines.append(f"  {r.role_id}: {r.role_name} — {r.responsibility}")
    else:
        lines.append("  none")

    lines.append("")
    lines.append("=== models ===")
    if snapshot.models:
        for m in snapshot.models:
            lines.append(f"  {m.model_id}: {m.display_name} ({m.provider}/{m.source})")
    else:
        lines.append("  none")

    lines.append("")
    lines.append("=== assignments ===")
    if snapshot.assignments:
        for a in snapshot.assignments:
            lines.append(
                f"  {a.role_id} → {a.model_id} "
                f"[mode={a.assignment_mode} health={a.assignment_health}]"
            )
    else:
        lines.append("  none")

    lines.append("")
    lines.append("=== conflicts ===")
    if snapshot.conflicts:
        for c in snapshot.conflicts:
            lines.append(f"  [{c.severity}] {c.title}: {c.description}")
    else:
        lines.append("  none")

    lines.append("")
    lines.append("=== fallback ===")
    fb = snapshot.fallback
    lines.append(
        f"fallback_active={fb.fallback_active} "
        f"local_fallback_ready={fb.local_fallback_ready} "
        f"degraded_roles={fb.degraded_roles or 'none'} "
        f"operator_message={fb.operator_message}"
    )

    lines.append("")
    lines.append("=== pending_review ===")
    pr = snapshot.pending_review
    if pr is not None:
        lines.append(
            f"review_id={pr.review_id} role={pr.role_id} "
            f"current={pr.current_model_id} → proposed={pr.proposed_model_id} "
            f"severity={pr.severity} summary={pr.summary}"
        )
    else:
        lines.append("  none")

    if role_id == "chief-agent" and session is not None:
        if snapshot.roles:
            all_role_ids = [r.role_id for r in snapshot.roles]
        else:
            all_role_ids = [
                "market-scanner",
                "news-sentiment-agent",
                "forecast-model",
            ]
        subagent_role_ids = [rid for rid in all_role_ids if rid != "chief-agent"]

        repo = OpsRepository(session)
        runs = repo.list_latest_agent_runs(subagent_role_ids)

        lines.append("")
        lines.append("=== subagent_reports ===")

        if not runs:
            lines.append("  no recent reports")
        else:
            now = datetime.now(UTC)
            for rid in subagent_role_ids:
                run = runs.get(rid)
                if run is None:
                    continue
                age_min = int((now - run.created_at).total_seconds() / 60)
                content_text = run.content or ""
                if len(content_text) > 2000:
                    content_text = content_text[:2000] + "...[truncated]"
                lines.append(f"  [{rid}] ({age_min} min ago):")
                lines.append(f"    {content_text}")

    return "\n".join(lines)


class AIAgentCycleJob:
    """Periodic job: snapshot → render → run_agent → persist.

    Runs on the event loop (``executor="async"``). Each tick is
    concurrency-guarded by an ``asyncio.Lock`` — overlapping cycles
    are silently skipped.
    """

    def __init__(
        self,
        *,
        runner: AgentRunner,
        session_factory: sessionmaker,
        role_ids: list[str],
        ai_control_service: AIControlService,
    ) -> None:
        self._runner = runner
        self._session_factory = session_factory
        self._role_ids = role_ids
        self._ai_control_service = ai_control_service
        self._lock = asyncio.Lock()

    async def run_once(self) -> None:
        """Execute one agent cycle: snapshot → render → run → persist.

        Iterates over all configured role_ids **sequentially** (one
        ``asyncio.Lock`` per tick, no parallelism). Per-role isolation:
        a ``ModelUnavailableError`` on role N records an error row and
        continues to role N+1; other exceptions propagate to
        ``_arun_safely``.
        """
        if self._lock.locked():
            logger.warning("clay.scheduler: ai-agent-cycle already running, skip tick")
            return

        async with self._lock:
            snapshot = await asyncio.to_thread(self._build_snapshot)
            for role_id in self._role_ids:
                if role_id == "chief-agent":
                    with self._session_factory() as s:
                        context = _render_context(snapshot, role_id, session=s)
                else:
                    context = _render_context(snapshot, role_id)
                try:
                    result = await self._runner.run_agent(role_id, context)
                except ModelUnavailableError as exc:
                    logger.warning(
                        "clay.scheduler: ai-agent-cycle ModelUnavailableError "
                        "for role=%s: %s",
                        role_id,
                        exc,
                    )
                    await asyncio.to_thread(
                        self._persist_error,
                        created_at=datetime.now(UTC),
                        role_id=role_id,
                        model_id=getattr(exc, "model_id", None) or "unresolved",
                        error=str(exc),
                    )
                    continue

                await asyncio.to_thread(
                    self._persist_success,
                    created_at=datetime.now(UTC),
                    role_id=role_id,
                    model_id=result.model_id,
                    content=result.content,
                    thinking=result.thinking,
                )

    def _build_snapshot(self) -> AIControlSnapshot:
        """Sync block: open session, call build_snapshot, close."""
        session = self._session_factory()
        try:
            return self._ai_control_service.build_snapshot(session)
        finally:
            session.close()

    def _persist_success(
        self,
        *,
        created_at: datetime,
        role_id: str,
        model_id: str,
        content: str,
        thinking: str | None,
    ) -> None:
        """Sync block: persist a successful run result."""
        session = self._session_factory()
        try:
            run = AIAgentRun(
                created_at=created_at,
                role_id=role_id,
                model_id=model_id,
                content=content,
                thinking=thinking,
                error=None,
            )
            session.add(run)
            session.commit()
        finally:
            session.close()

    def _persist_error(
        self,
        *,
        created_at: datetime,
        role_id: str,
        model_id: str,
        error: str,
    ) -> None:
        """Sync block: persist a failed (ModelUnavailableError) run."""
        session = self._session_factory()
        try:
            run = AIAgentRun(
                created_at=created_at,
                role_id=role_id,
                model_id=model_id,
                content=None,
                thinking=None,
                error=error,
            )
            session.add(run)
            session.commit()
        finally:
            session.close()
