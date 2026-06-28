"""Add source to unique constraints — market_bars + freshness_status.

market_bars: expand UC (source, symbol, timeframe, bar_open_time),
drop server_default on source.
market_freshness_status: ADD COLUMN source, backfill, expand UC.
orderbook_summaries: NOT touched (dormant, E3 if needed).

Revision ID: 0010_e2_source_in_identity
Revises: 0009_context_unique_dedup
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0010_e2_source_in_identity"
down_revision: str | None = "0009_context_unique_dedup"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # market_bars — hypertable без компрессии, DDL безопасен
    op.execute("ALTER TABLE market.market_bars DROP CONSTRAINT uq_market_bar")
    op.execute(
        "ALTER TABLE market.market_bars "
        "ADD CONSTRAINT uq_market_bar "
        "UNIQUE (source, symbol, timeframe, bar_open_time)"
    )
    op.execute("ALTER TABLE market.market_bars ALTER COLUMN source DROP DEFAULT")

    # market_freshness_status — обычная PG
    op.execute(
        "ALTER TABLE market.market_freshness_status "
        "ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'binance_spot'"
    )
    op.execute(
        "ALTER TABLE market.market_freshness_status ALTER COLUMN source DROP DEFAULT"
    )
    op.execute(
        "ALTER TABLE market.market_freshness_status "
        "DROP CONSTRAINT uq_market_freshness_status"
    )
    op.execute(
        "ALTER TABLE market.market_freshness_status "
        "ADD CONSTRAINT uq_market_freshness_status "
        "UNIQUE (source, symbol, timeframe)"
    )


def downgrade() -> None:
    # market_freshness_status — восстановить old UC, удалить source
    op.execute(
        "ALTER TABLE market.market_freshness_status "
        "DROP CONSTRAINT uq_market_freshness_status"
    )
    op.execute(
        "ALTER TABLE market.market_freshness_status "
        "ADD CONSTRAINT uq_market_freshness_status "
        "UNIQUE (symbol, timeframe)"
    )
    op.execute("ALTER TABLE market.market_freshness_status DROP COLUMN source")

    # market_bars — восстановить server_default + old UC
    op.execute(
        "ALTER TABLE market.market_bars ALTER COLUMN source SET DEFAULT 'binance_spot'"
    )
    op.execute("ALTER TABLE market.market_bars DROP CONSTRAINT uq_market_bar")
    op.execute(
        "ALTER TABLE market.market_bars "
        "ADD CONSTRAINT uq_market_bar "
        "UNIQUE (symbol, timeframe, bar_open_time)"
    )
