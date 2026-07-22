"""market_bars continuous aggregate: 1h→1d OHLCV (D-13 #4)

Revision ID: 0031_market_bars_cagg
Revises: 0030_market_bars_retention
Create Date: 2026-07-22

Create a TimescaleDB continuous aggregate ``market.market_bars_1d``
that downsamples the ``1h`` bars into daily OHLCV.

Refresh policy is ON (start_offset 3d, end_offset 1h, schedule 1h)
because the CAGG is non-destructive: write-path and raw data are
untouched.  The CAGG is dormant at the application layer.

SQLite-guard: upgrade/downgrade are no-ops on SQLite (CI safety).
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0031_market_bars_cagg"
down_revision: str | None = "0030_market_bars_retention"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    op.execute(
        "CREATE MATERIALIZED VIEW IF NOT EXISTS market.market_bars_1d "
        "WITH (timescaledb.continuous) AS "
        "SELECT "
        "    time_bucket(INTERVAL '1 day', bar_open_time) AS bucket, "
        "    symbol, "
        "    source, "
        "    first(open,  bar_open_time) AS open, "
        "    max(high)                   AS high, "
        "    min(low)                    AS low, "
        "    last(close,  bar_open_time) AS close, "
        "    sum(volume)                 AS volume, "
        "    sum(quote_volume)           AS quote_volume "
        "FROM market.market_bars "
        "WHERE timeframe = '1h' "
        "GROUP BY bucket, symbol, source "
        "WITH NO DATA"
    )
    op.execute(
        "SELECT add_continuous_aggregate_policy("
        "  'market.market_bars_1d',"
        "  start_offset    => INTERVAL '3 days',"
        "  end_offset      => INTERVAL '1 hour',"
        "  schedule_interval => INTERVAL '1 hour',"
        "  if_not_exists   => TRUE"
        ")"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    op.execute(
        "SELECT remove_continuous_aggregate_policy("
        "  'market.market_bars_1d',"
        "  if_exists => TRUE"
        ")"
    )
    op.execute("DROP MATERIALIZED VIEW IF EXISTS market.market_bars_1d")
