"""add ops runtime state

Revision ID: 0008_ops_runtime_state
Revises: 0007_incident_lifecycle
Create Date: 2026-06-01 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008_ops_runtime_state"
down_revision: str | None = "0007_incident_lifecycle"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. ai_assignments — multi-row, one row per role (role_id = PK)
    op.create_table(
        "ai_assignments",
        sa.Column("role_id", sa.String(length=64), primary_key=True),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        schema="ops",
    )

    # 2. ai_control_state — singleton (id=1)
    op.create_table(
        "ai_control_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_review_id", sa.String(length=64), nullable=True),
        sa.Column("pending_review_role_id", sa.String(length=64), nullable=True),
        sa.Column("pending_review_model_id", sa.String(length=64), nullable=True),
        sa.Column(
            "pending_review_created_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.CheckConstraint("id = 1", name="ck_ops_ai_control_state_singleton"),
        schema="ops",
    )

    # 3. session_state — singleton (id=1), active + pending fields
    op.create_table(
        "session_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("current_pair_symbol", sa.String(length=32), nullable=True),
        sa.Column("current_signal_id", sa.String(length=64), nullable=True),
        sa.Column("strategy_mode", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_replacement_id", sa.String(length=64), nullable=True),
        sa.Column("pending_current_symbol", sa.String(length=32), nullable=True),
        sa.Column("pending_proposed_symbol", sa.String(length=32), nullable=True),
        sa.Column("pending_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_ops_session_state_singleton"),
        schema="ops",
    )

    # 4. workspace_focus — singleton (id=1)
    op.create_table(
        "workspace_focus",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("focus_symbol", sa.String(length=32), nullable=True),
        sa.Column(
            "focus_source",
            sa.String(length=32),
            nullable=False,
            server_default="system_recommendation",
        ),
        sa.Column("selected_signal_id", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("id = 1", name="ck_ops_workspace_focus_singleton"),
        schema="ops",
    )

    # 5. strategy_state — singleton (id=1)
    op.create_table(
        "strategy_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "strategy_mode",
            sa.String(length=32),
            nullable=False,
            server_default="momentum",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("id = 1", name="ck_ops_strategy_state_singleton"),
        schema="ops",
    )

    # 6. reliability_state — singleton (id=1)
    op.create_table(
        "reliability_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_rechecked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_ops_reliability_state_singleton"),
        schema="ops",
    )


def downgrade() -> None:
    op.drop_table("reliability_state", schema="ops")
    op.drop_table("strategy_state", schema="ops")
    op.drop_table("workspace_focus", schema="ops")
    op.drop_table("session_state", schema="ops")
    op.drop_table("ai_control_state", schema="ops")
    op.drop_table("ai_assignments", schema="ops")
