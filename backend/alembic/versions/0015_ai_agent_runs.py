"""ops.ai_agent_runs: persistence for agent-run turns

Revision ID: 0015_ai_agent_runs
Revises: 0014_hypertable_indexes
Create Date: 2026-06-11

DEPLOY-5 / 5b-ii.2b-i.
"""

from alembic import op
import sqlalchemy as sa

from clay.db.types import UTCDateTime

revision = "0015_ai_agent_runs"
down_revision = "0014_hypertable_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("thinking", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        schema="ops",
    )


def downgrade() -> None:
    op.drop_table("ai_agent_runs", schema="ops")
