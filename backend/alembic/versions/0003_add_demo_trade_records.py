"""Add demo trade tracking tables."""

from alembic import op
import sqlalchemy as sa


revision = "0003_e8_demo_tracking"
down_revision = "0002_e2_hypertables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS demo")
    op.create_table(
        "demo_trade_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("signal_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("executed_symbol", sa.String(length=32), nullable=True),
        sa.Column("operator_action", sa.String(length=32), nullable=False),
        sa.Column("operator_notes", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_trade_id", sa.String(length=128), nullable=True),
        sa.Column("broker_status", sa.String(length=32), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "outcome_status",
            sa.String(length=32),
            nullable=False,
            server_default="unresolved",
        ),
        schema="demo",
    )
    op.create_index(
        "ix_demo_trade_records_session_id",
        "demo_trade_records",
        ["session_id"],
        unique=False,
        schema="demo",
    )
    op.create_index(
        "ix_demo_trade_records_signal_id",
        "demo_trade_records",
        ["signal_id"],
        unique=False,
        schema="demo",
    )
    op.create_index(
        "ix_demo_trade_records_symbol",
        "demo_trade_records",
        ["symbol"],
        unique=False,
        schema="demo",
    )
    op.create_index(
        "ix_demo_trade_records_executed_symbol",
        "demo_trade_records",
        ["executed_symbol"],
        unique=False,
        schema="demo",
    )
    op.create_index(
        "ix_demo_trade_records_operator_action",
        "demo_trade_records",
        ["operator_action"],
        unique=False,
        schema="demo",
    )
    op.create_index(
        "ix_demo_trade_records_recorded_at",
        "demo_trade_records",
        ["recorded_at"],
        unique=False,
        schema="demo",
    )
    op.create_index(
        "ix_demo_trade_records_external_trade_id",
        "demo_trade_records",
        ["external_trade_id"],
        unique=False,
        schema="demo",
    )
    op.create_index(
        "ix_demo_trade_records_broker_status",
        "demo_trade_records",
        ["broker_status"],
        unique=False,
        schema="demo",
    )
    op.create_index(
        "ix_demo_trade_records_observed_at",
        "demo_trade_records",
        ["observed_at"],
        unique=False,
        schema="demo",
    )
    op.create_index(
        "ix_demo_trade_records_outcome_status",
        "demo_trade_records",
        ["outcome_status"],
        unique=False,
        schema="demo",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_demo_trade_records_outcome_status",
        table_name="demo_trade_records",
        schema="demo",
    )
    op.drop_index(
        "ix_demo_trade_records_observed_at",
        table_name="demo_trade_records",
        schema="demo",
    )
    op.drop_index(
        "ix_demo_trade_records_broker_status",
        table_name="demo_trade_records",
        schema="demo",
    )
    op.drop_index(
        "ix_demo_trade_records_external_trade_id",
        table_name="demo_trade_records",
        schema="demo",
    )
    op.drop_index(
        "ix_demo_trade_records_recorded_at",
        table_name="demo_trade_records",
        schema="demo",
    )
    op.drop_index(
        "ix_demo_trade_records_operator_action",
        table_name="demo_trade_records",
        schema="demo",
    )
    op.drop_index(
        "ix_demo_trade_records_executed_symbol",
        table_name="demo_trade_records",
        schema="demo",
    )
    op.drop_index(
        "ix_demo_trade_records_symbol", table_name="demo_trade_records", schema="demo"
    )
    op.drop_index(
        "ix_demo_trade_records_signal_id",
        table_name="demo_trade_records",
        schema="demo",
    )
    op.drop_index(
        "ix_demo_trade_records_session_id",
        table_name="demo_trade_records",
        schema="demo",
    )
    op.drop_table("demo_trade_records", schema="demo")
