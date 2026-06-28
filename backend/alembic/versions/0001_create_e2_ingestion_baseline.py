"""Create E2 ingestion baseline schemas and tables."""

from alembic import op
import sqlalchemy as sa


revision = "0001_e2_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS market")
    op.execute("CREATE SCHEMA IF NOT EXISTS context")
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "market_bars",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("quote_volume", sa.Float(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="binance_spot",
        ),
        sa.Column("bar_open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bar_close_time", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "bar_open_time"),
        sa.UniqueConstraint(
            "symbol", "timeframe", "bar_open_time", name="uq_market_bar"
        ),
        schema="market",
    )

    op.create_table(
        "orderbook_summaries",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("best_bid", sa.Float(), nullable=False),
        sa.Column("best_ask", sa.Float(), nullable=False),
        sa.Column("bid_depth_top", sa.Float(), nullable=True),
        sa.Column("ask_depth_top", sa.Float(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="binance_spot",
        ),
        sa.PrimaryKeyConstraint("id", "captured_at"),
        schema="market",
    )

    op.create_table(
        "market_freshness_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("freshness_state", sa.String(length=32), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_bar_open_time", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("symbol", "timeframe", name="uq_market_freshness_status"),
        schema="market",
    )

    op.create_table(
        "news_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("headline", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        schema="context",
    )

    op.create_table(
        "sentiment_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("sentiment_label", sa.String(length=32), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        schema="context",
    )

    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        schema="ops",
    )

    op.create_table(
        "connector_status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connector_id", sa.String(length=64), nullable=False),
        sa.Column("connector_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=True),
        schema="ops",
    )

    op.create_table(
        "source_health_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        schema="ops",
    )


def downgrade() -> None:
    op.drop_table("source_health_events", schema="ops")
    op.drop_table("connector_status_history", schema="ops")
    op.drop_table("ingest_runs", schema="ops")
    op.drop_table("sentiment_snapshots", schema="context")
    op.drop_table("news_items", schema="context")
    op.drop_table("market_freshness_status", schema="market")
    op.drop_table("orderbook_summaries", schema="market")
    op.drop_table("market_bars", schema="market")
