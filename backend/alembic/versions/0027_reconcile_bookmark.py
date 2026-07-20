"""reconcile_bookmark: durable cursor for fills reconciliation (D-12b-2)

Revision ID: 0027_reconcile_bookmark
Revises: 0026_order_ledger_schema
Create Date: 2026-07-19

Additive only: new table ``reconcile_bookmark`` in ops schema.
Tracks last processed trade_id per (venue, entity_type, symbol) for
incremental fill-ingestion replay.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0027_reconcile_bookmark"
down_revision: str | None = "0026_order_ledger_schema"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.execute("CREATE SCHEMA IF NOT EXISTS ops")

    op.create_table(
        "reconcile_bookmark",
        sa.Column(
            "bookmark_pk",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("venue", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("last_trade_id", sa.String(64), nullable=True),
        sa.Column("last_timestamp", sa.BigInteger, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "venue",
            "entity_type",
            "symbol",
            name="uq_reconcile_bookmark_venue_entity_symbol",
        ),
        schema="ops",
    )


def downgrade() -> None:
    op.drop_table("reconcile_bookmark", schema="ops")
