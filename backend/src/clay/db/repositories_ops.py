import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlalchemy import func

from clay.db.models_ops import (
    AIAgentRun,
    ConnectorStatusHistory,
    ExecutionOverride,
    IngestRun,
    SourceHealthEvent,
)


class OpsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_ingest_run(
        self,
        *,
        source_name: str,
        source_type: str,
        status: str,
        started_at: datetime,
        details: dict[str, Any] | None = None,
    ) -> IngestRun:
        run = IngestRun(
            source_name=source_name,
            source_type=source_type,
            status=status,
            started_at=started_at,
            details_json=self._serialize_details(details),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def finalize_ingest_run(
        self,
        run: IngestRun,
        *,
        status: str,
        finished_at: datetime,
        details: dict[str, Any] | None = None,
    ) -> None:
        run.status = status
        run.finished_at = finished_at
        run.details_json = self._serialize_details(details)
        self.session.flush()

    def record_connector_status(
        self,
        *,
        connector_id: str,
        connector_type: str,
        status: str,
        observed_at: datetime,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            ConnectorStatusHistory(
                connector_id=connector_id,
                connector_type=connector_type,
                status=status,
                observed_at=observed_at,
                details_json=self._serialize_details(details),
            ),
        )
        self.session.flush()

    def record_source_health_event(
        self,
        *,
        source_name: str,
        severity: str,
        message: str,
        recorded_at: datetime,
    ) -> None:
        self.session.add(
            SourceHealthEvent(
                source_name=source_name,
                severity=severity,
                lifecycle_status="active",
                message=message,
                recorded_at=recorded_at,
                resolved_at=None,
                resolution_message=None,
            ),
        )
        self.session.flush()

    def resolve_source_health_events(
        self,
        *,
        source_name: str,
        resolved_at: datetime,
        resolution_message: str,
    ) -> int:
        query = select(SourceHealthEvent).where(
            SourceHealthEvent.source_name == source_name,
            SourceHealthEvent.lifecycle_status == "active",
        )
        active_rows = list(self.session.scalars(query).all())
        for row in active_rows:
            row.lifecycle_status = "resolved"
            row.resolved_at = resolved_at
            row.resolution_message = resolution_message
        self.session.flush()
        return len(active_rows)

    def latest_connector_statuses(self) -> list[ConnectorStatusHistory]:
        query = select(ConnectorStatusHistory).order_by(
            ConnectorStatusHistory.observed_at.desc(),
        )
        all_rows = list(self.session.scalars(query).all())
        deduped: list[ConnectorStatusHistory] = []
        seen: set[str] = set()
        for row in all_rows:
            if row.connector_id in seen:
                continue
            deduped.append(row)
            seen.add(row.connector_id)
        return deduped

    def latest_incidents(
        self,
        *,
        limit: int = 10,
        active_only: bool = True,
    ) -> list[SourceHealthEvent]:
        query = select(SourceHealthEvent)
        if active_only:
            query = query.where(SourceHealthEvent.lifecycle_status == "active")
        query = query.order_by(
            SourceHealthEvent.recorded_at.desc(),
        ).limit(limit)
        return list(self.session.scalars(query).all())

    def latest_ingest_run(self) -> IngestRun | None:
        """Return the most recent ``IngestRun`` by ``started_at``, or ``None``."""
        return self.session.scalar(
            select(IngestRun).order_by(IngestRun.started_at.desc()).limit(1),
        )

    def list_latest_agent_runs(self, role_ids: list[str]) -> dict[str, AIAgentRun]:
        if not role_ids:
            return {}

        stmt = (
            select(AIAgentRun)
            .where(
                AIAgentRun.role_id.in_(role_ids),
                AIAgentRun.error.is_(None),
                AIAgentRun.content.isnot(None),
                AIAgentRun.content != "",
            )
            .order_by(AIAgentRun.created_at.desc())
        )
        rows = list(self.session.scalars(stmt).all())

        result: dict[str, AIAgentRun] = {}
        for row in rows:
            if row.role_id not in result:
                result[row.role_id] = row
        return result

    def agent_runs_stats(
        self, role_ids: list[str], *, since: datetime
    ) -> dict[str, dict[str, int]]:
        """Return per-role stats within *since* window.

        Returns dict[role_id, {total: int, errored: int}].
        """
        if not role_ids:
            return {}

        total_stmt = (
            select(
                AIAgentRun.role_id,
                func.count(AIAgentRun.id).label("total"),
                func.count(AIAgentRun.error).label("errored"),
            )
            .where(
                AIAgentRun.role_id.in_(role_ids),
                AIAgentRun.created_at >= since,
            )
            .group_by(AIAgentRun.role_id)
        )
        rows = self.session.execute(total_stmt).all()
        result: dict[str, dict[str, int]] = {
            role_id: {"total": 0, "errored": 0} for role_id in role_ids
        }
        for row in rows:
            result[row.role_id] = {"total": int(row.total), "errored": int(row.errored)}
        return result

    def _serialize_details(self, details: dict[str, Any] | None) -> str | None:
        if details is None:
            return None
        return json.dumps(details, sort_keys=True, default=str)


class OverrideRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, event: ExecutionOverride) -> None:
        self.session.add(event)
        self.session.flush()

    def list_by_override_id(self, override_id: str) -> list[ExecutionOverride]:
        stmt = (
            select(ExecutionOverride)
            .where(ExecutionOverride.override_id == override_id)
            .order_by(ExecutionOverride.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())

    def latest_for_override(self, override_id: str) -> ExecutionOverride | None:
        stmt = (
            select(ExecutionOverride)
            .where(ExecutionOverride.override_id == override_id)
            .order_by(ExecutionOverride.created_at.desc())
            .limit(1)
        )
        return self.session.scalar(stmt)
