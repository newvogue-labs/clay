"""halt_latch: durable halt-latch for execution-gate (D-12d D4)

Revision ID: 0028_halt_latch
Revises: 0027_reconcile_bookmark
Create Date: 2026-07-20

Additive only: new table ``halt_latch`` in ops schema.
Singleton pattern — one row, engaged/disengaged by operator action.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0028_halt_latch"
down_revision: str | None = "0027_reconcile_bookmark"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.execute("CREATE SCHEMA IF NOT EXISTS ops")

    op.create_table(
        "halt_latch",
        sa.Column(
            "latch_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "engaged",
            sa.Boolean,
            nullable=False,
            server_default="0",
        ),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("engaged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_reason", sa.Text, nullable=True),
        schema="ops",
    )


def downgrade() -> None:
    op.drop_table("halt_latch", schema="ops")
