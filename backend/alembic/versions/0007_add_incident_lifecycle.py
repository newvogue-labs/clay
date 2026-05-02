"""add incident lifecycle

Revision ID: 0007_incident_lifecycle
Revises: 0006_e11_validation
Create Date: 2026-04-22 20:30:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007_incident_lifecycle"
down_revision: str | None = "0006_e11_validation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_health_events",
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="active"),
        schema="ops",
    )
    op.add_column(
        "source_health_events",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        schema="ops",
    )
    op.add_column(
        "source_health_events",
        sa.Column("resolution_message", sa.Text(), nullable=True),
        schema="ops",
    )
    op.create_index(
        "ix_ops_source_health_events_lifecycle_status",
        "source_health_events",
        ["lifecycle_status"],
        unique=False,
        schema="ops",
    )


def downgrade() -> None:
    op.drop_index("ix_ops_source_health_events_lifecycle_status", table_name="source_health_events", schema="ops")
    op.drop_column("source_health_events", "resolution_message", schema="ops")
    op.drop_column("source_health_events", "resolved_at", schema="ops")
    op.drop_column("source_health_events", "lifecycle_status", schema="ops")
