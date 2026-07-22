"""market_bars compression: native TimescaleDB compression policy (D-13 #2)

Revision ID: 0029_market_bars_compression
Revises: 0028_halt_latch
Create Date: 2026-07-22

Enable native TimescaleDB compression on ``market.market_bars``
with a 7-day ``compress_after`` policy.  Non-destructive — data
is preserved, reads are transparent.

SQLite-guard: upgrade/downgrade are no-ops on SQLite (CI safety).
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text


revision: str = "0029_market_bars_compression"
down_revision: str | None = "0028_halt_latch"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    op.execute(
        "ALTER TABLE market.market_bars SET ("
        "  timescaledb.compress = true,"
        "  timescaledb.compress_segmentby = 'symbol, timeframe',"
        "  timescaledb.compress_orderby = 'bar_open_time DESC'"
        ")"
    )
    op.execute(
        "SELECT add_compression_policy("
        "  'market.market_bars',"
        "  compress_after => INTERVAL '7 days',"
        "  if_not_exists => TRUE"
        ")"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    op.execute(
        "SELECT remove_compression_policy(  'market.market_bars',  if_exists => TRUE)"
    )
    # Decompress all compressed chunks before disabling the flag.
    # Query compressed chunks via information view, then decompress one
    # by one.  Avoids PL/pgSQL format() which clashes with SQLAlchemy's
    # percent-escaping in op.execute().
    rows = bind.execute(
        text(
            "SELECT chunk_schema, chunk_name "
            "FROM timescaledb_information.chunks "
            "WHERE hypertable_name = 'market_bars' "
            "  AND hypertable_schema = 'market' "
            "  AND is_compressed = true"
        )
    ).fetchall()
    for schema, chunk in rows:
        op.execute(f"SELECT decompress_chunk('{schema}.{chunk}', true)")
    op.execute("ALTER TABLE market.market_bars SET (  timescaledb.compress = false)")
