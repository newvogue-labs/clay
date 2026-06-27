from datetime import datetime

from sqlalchemy import CheckConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from clay.db.base import Base
from clay.db.types import UTCDateTime


class IngestRun(Base):
    __tablename__ = "ingest_runs"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConnectorStatusHistory(Base):
    __tablename__ = "connector_status_history"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_id: Mapped[str] = mapped_column(String(64), index=True)
    connector_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceHealthEvent(Base):
    __tablename__ = "source_health_events"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(32), index=True, default="active"
    )
    message: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolution_message: Mapped[str | None] = mapped_column(Text, nullable=True)


# === Wave A / Slice A1: ops runtime state persistence (2026-06-01) ===
# See alembic revision 0008_ops_runtime_state. Tables here mirror the in-memory
# state that lives in: ai_control, session_control, workspace, validation_lab,
# reliability. Five of these tables are singletons (CHECK id = 1).
#
# Slice A2.5 (2026-06-01): all datetime columns on the runtime-state tables
# are typed as ``UTCDateTime`` (see ``clay.db.types``) so that round-trips
# against SQLite preserve a UTC ``tzinfo`` (PostgreSQL would already do
# this; SQLite returns naive ``datetime`` otherwise).
#
# Slice FIX-B (2026-06-04): the 3 legacy ``ops``-schema tables above
# (``ingest_runs``, ``connector_status_history``, ``source_health_events``)
# are also migrated to ``UTCDateTime``. Their on-disk column type does
# NOT change (UTCDateTime.impl = DateTime(timezone=True)), so no alembic
# migration is required — the autogenerate diff is empty. Pre-fix, the
# raw ``DateTime(timezone=True)`` columns round-tripped as naive on
# SQLite, which caused latent TypeError on every code path that
# compared the value with ``datetime.now(UTC)`` (notably
# ``/health/ready`` last-ingest staleness and ``OpsRetentionJob.run``).


class AIAssignment(Base):
    __tablename__ = "ai_assignments"
    __table_args__ = {"schema": "ops"}

    role_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AIControlState(Base):
    __tablename__ = "ai_control_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_ops_ai_control_state_singleton"),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )
    pending_review_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pending_review_role_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    pending_review_model_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    pending_review_created_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )


class SessionState(Base):
    __tablename__ = "session_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_ops_session_state_singleton"),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_pair_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_signal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    pending_replacement_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    pending_current_symbol: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    pending_proposed_symbol: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    pending_created_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )


class WorkspaceFocus(Base):
    __tablename__ = "workspace_focus"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_ops_workspace_focus_singleton"),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    focus_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    focus_source: Mapped[str] = mapped_column(String(32))
    selected_signal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class StrategyState(Base):
    __tablename__ = "strategy_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_ops_strategy_state_singleton"),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_mode: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ReliabilityState(Base):
    __tablename__ = "reliability_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_ops_reliability_state_singleton"),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    last_rechecked_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )


class AIAgentRun(Base):
    """Persisted record of a single AgentRunner.run_agent turn (DEPLOY-5 / 5b-ii.2b).

    `content`/`thinking` are populated on success; `error` is populated when the
    turn failed loud (e.g. ModelUnavailableError). Timestamps are set from code,
    matching the ops-schema convention (no server_default).
    """

    __tablename__ = "ai_agent_runs"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    role_id: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(128))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExecutionOverride(Base):
    """INSERT-only audit journal for execution_overrides (S-EXEC-3b).

    Logs every state-transition of the execution override lifecycle:
    requested → confirmed → revoked → expired. Rows are never updated or
    deleted — append-only for audit fidelity. `audit_id` ties back to the
    originating audit trail, `expires_at` marks the TTL of the armed state.

    Surrogate PK (`event_id`) keeps identity stable and collision-free
    even under fixed VirtualClock (no hidden dependency on `created_at`
    uniqueness).
    """

    __tablename__ = "execution_overrides"
    __table_args__ = (
        Index("ix_execution_overrides_override_created_at", "override_id", "created_at"),
        Index("ix_execution_overrides_actor_created_at", "actor", "created_at"),
        {"schema": "ops"},
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    override_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    mode_before: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mode_after: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    audit_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
