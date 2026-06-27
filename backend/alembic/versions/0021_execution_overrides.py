"""add ops.execution_overrides table (S-EXEC-3b — override audit journal)

Revision ID: 0021_execution_overrides
Revises: 0020_demo_trade_source
Create Date: 2026-06-27

INSERT-only audit journal for execution override lifecycle events.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0021_execution_overrides"
down_revision: str | None = "0020_demo_trade_source"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_overrides",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("override_id", sa.String(36), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("mode_before", sa.String(32), nullable=True),
        sa.Column("mode_after", sa.String(32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_id", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("event_id", name="pk_execution_overrides"),
        schema="ops",
    )
    op.create_index(
        "ix_execution_overrides_override_created_at",
        "execution_overrides",
        ["override_id", "created_at"],
        schema="ops",
    )
    op.create_index(
        "ix_execution_overrides_actor_created_at",
        "execution_overrides",
        ["actor", "created_at"],
        schema="ops",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_execution_overrides_actor_created_at",
        table_name="execution_overrides",
        schema="ops",
    )
    op.drop_table("execution_overrides", schema="ops")
