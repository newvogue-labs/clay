"""add source column to demo.demo_trade_records (S-REPLAY-3 — provenance)

Revision ID: 0020_demo_trade_provenance_source
Revises: 0019_ai_agent_runs_indexes
Create Date: 2026-06-25

Adds a VARCHAR(16) source column with a backfill of existing rows:
- baseline (first 20 sessions, ids 1-21 with a gap at 5)
- live (session #22, id=22)

The column is then set NOT NULL with server_default='live'
so all future records are automatically 'live'.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0020_demo_trade_source"
down_revision: str | None = "0019_ai_agent_runs_indexes"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. ADD COLUMN — nullable first
    op.add_column(
        "demo_trade_records",
        sa.Column("source", sa.String(16), nullable=True),
        schema="demo",
    )

    # 2. Backfill existing rows (R1: record_id boundary)
    #    Baseline = ids 1-21 (has gap at 5, gives exactly 20 rows)
    #    Live    = id 22 (the S-LIVE-DEMO-2 live session)
    op.execute("UPDATE demo.demo_trade_records SET source = 'baseline' WHERE id <= 21")
    op.execute("UPDATE demo.demo_trade_records SET source = 'live' WHERE id = 22")

    # 3. SET NOT NULL + server_default for future rows
    op.alter_column(
        "demo_trade_records",
        "source",
        nullable=False,
        server_default=sa.text("'live'"),
        schema="demo",
    )


def downgrade() -> None:
    op.drop_column("demo_trade_records", "source", schema="demo")
