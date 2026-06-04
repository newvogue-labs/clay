import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from clay.db.models_ops import ConnectorStatusHistory, IngestRun, SourceHealthEvent


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

    def _serialize_details(self, details: dict[str, Any] | None) -> str | None:
        if details is None:
            return None
        return json.dumps(details, sort_keys=True, default=str)
