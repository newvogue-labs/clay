"""add advisory_size_pct column to demo.demo_trade_records (S-KELLY-2)

Revision ID: 0018_demo_advisory_size_pct
Revises: 0017_demo_open_session_uniq
Create Date: 2026-06-24

Adds a nullable DOUBLE PRECISION column for the Kelly-recommended
position size at time of logging (advisory, for audit trail).
Existing 20+ rows get NULL by default — backward-compatible.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0018_demo_advisory_size_pct"
down_revision: str | None = "0017_demo_open_session_uniq"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "demo_trade_records",
        sa.Column("advisory_size_pct", sa.Float(), nullable=True),
        schema="demo",
    )


def downgrade() -> None:
    op.drop_column("demo_trade_records", "advisory_size_pct", schema="demo")
