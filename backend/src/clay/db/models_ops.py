from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from clay.db.base import Base


class IngestRun(Base):
    __tablename__ = "ingest_runs"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConnectorStatusHistory(Base):
    __tablename__ = "connector_status_history"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_id: Mapped[str] = mapped_column(String(64), index=True)
    connector_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceHealthEvent(Base):
    __tablename__ = "source_health_events"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    message: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_message: Mapped[str | None] = mapped_column(Text, nullable=True)
