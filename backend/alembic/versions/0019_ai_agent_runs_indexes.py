"""add indexes to ops.ai_agent_runs (I1 role_id+created_at, I2 model_id+created_at)

Revision ID: 0019_ai_agent_runs_indexes
Revises: 0018_demo_advisory_size_pct
Create Date: 2026-06-24

Adds two btree indexes on query hot-paths:
- I1 (role_id, created_at DESC) — latest-run fetch + per-role error stats
- I2 (model_id, created_at DESC) — RPD budget check before session start
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0019_ai_agent_runs_indexes"
down_revision: str | None = "0018_demo_advisory_size_pct"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_ai_agent_runs_role_id_created_at",
        "ai_agent_runs",
        ["role_id", sa.text("created_at DESC")],
        schema="ops",
        if_not_exists=True,
    )
    op.create_index(
        "ix_ai_agent_runs_model_id_created_at",
        "ai_agent_runs",
        ["model_id", sa.text("created_at DESC")],
        schema="ops",
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_agent_runs_role_id_created_at", schema="ops", if_exists=True)
    op.drop_index("ix_ai_agent_runs_model_id_created_at", schema="ops", if_exists=True)
