"""order-ledger schema: order_events, order_current_state, fills (D-12a)

Revision ID: 0026_order_ledger_schema
Revises: 0025_proof_semantic_hash
Create Date: 2026-07-19

Three append-only / current-state tables in ops schema that form the
foundation of the order journal.  Not yet wired to any production code —
schema + models + tests only.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0026_order_ledger_schema"
down_revision: str | None = "0025_proof_semantic_hash"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.execute("CREATE SCHEMA IF NOT EXISTS ops")

    # --- order_events (append-only journal) ---
    op.create_table(
        "order_events",
        sa.Column(
            "ledger_seq",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("event_id", sa.String(36), nullable=False, unique=True),
        sa.Column("client_order_id", sa.String(64), nullable=False),
        sa.Column("venue_order_id", sa.String(64), nullable=True),
        sa.Column("venue", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("semantic_hash", sa.String(16), nullable=True),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="ops",
    )
    op.create_index(
        "ix_order_events_client_order_id_ledger_seq",
        "order_events",
        ["client_order_id", "ledger_seq"],
        schema="ops",
    )
    op.create_index(
        "ix_order_events_venue_order_id",
        "order_events",
        ["venue_order_id"],
        schema="ops",
    )
    op.create_index(
        "ix_order_events_semantic_hash_created_at",
        "order_events",
        ["semantic_hash", "created_at"],
        schema="ops",
    )

    # --- order_current_state (singleton per order) ---
    op.create_table(
        "order_current_state",
        sa.Column("client_order_id", sa.String(64), primary_key=True),
        sa.Column("venue", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("venue_order_id", sa.String(64), nullable=True),
        sa.Column("lifecycle_state", sa.Text, nullable=False),
        sa.Column("filled_qty", sa.Text, nullable=False, server_default="0"),
        sa.Column("last_event_id", sa.String(36), nullable=False),
        sa.Column("semantic_hash", sa.String(16), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="ops",
    )
    op.create_index(
        "ix_order_current_state_semantic_hash",
        "order_current_state",
        ["semantic_hash"],
        schema="ops",
    )
    op.create_index(
        "ix_order_current_state_venue_venue_order_id",
        "order_current_state",
        ["venue", "venue_order_id"],
        schema="ops",
    )

    # --- fills (trade-level records) ---
    op.create_table(
        "fills",
        sa.Column(
            "fill_pk",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("venue", sa.String(32), nullable=False),
        sa.Column("trade_id", sa.String(64), nullable=False),
        sa.Column("venue_order_id", sa.String(64), nullable=False),
        sa.Column("client_order_id", sa.String(64), nullable=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("quantity", sa.Text, nullable=False),
        sa.Column("price", sa.Text, nullable=False),
        sa.Column("commission", sa.Text, nullable=True),
        sa.Column("commission_asset", sa.String(32), nullable=True),
        sa.Column("transact_time", sa.BigInteger, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("venue", "trade_id", name="uq_fills_venue_trade_id"),
        schema="ops",
    )
    op.create_index(
        "ix_fills_venue_order_id",
        "fills",
        ["venue_order_id"],
        schema="ops",
    )
    op.create_index(
        "ix_fills_client_order_id",
        "fills",
        ["client_order_id"],
        schema="ops",
    )


def downgrade() -> None:
    op.drop_table("fills", schema="ops")
    op.drop_table("order_current_state", schema="ops")
    op.drop_table("order_events", schema="ops")
