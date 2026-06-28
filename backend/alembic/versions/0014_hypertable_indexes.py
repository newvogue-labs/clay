"""create 4 hypertable indexes (G2.5c wave 2)

Closes the model-to-DB drift for the two TimescaleDB hypertables
(market.market_bars with 6 chunks, market.orderbook_summaries with 0).
TimescaleDB 2.x does NOT support ``CREATE INDEX CONCURRENTLY`` on a
hypertable parent -- the index is created on the parent and
propagated to all existing/future chunks under a brief
ACCESS EXCLUSIVE lock instead. On the empty R6 state this is
instant and safe. Downgrade drops the index the same way.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0014_hypertable_indexes"
down_revision: Union[str, None] = "0013_create_missing_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (schema, table, index_name, [columns]) -- NO-SCHEMA convention ix_<table>_<col>
_INDEXES: list[tuple[str, str, str, list[str]]] = [
    # market_bars (3)
    ("market", "market_bars", "ix_market_bars_bar_close_time", ["bar_close_time"]),
    ("market", "market_bars", "ix_market_bars_symbol", ["symbol"]),
    ("market", "market_bars", "ix_market_bars_timeframe", ["timeframe"]),
    # orderbook_summaries (1)
    ("market", "orderbook_summaries", "ix_orderbook_summaries_symbol", ["symbol"]),
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for schema, table, name, cols in _INDEXES:
            op.create_index(name, table, cols, schema=schema, if_not_exists=True)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for schema, table, name, cols in reversed(_INDEXES):
            op.drop_index(name, table_name=table, schema=schema, if_exists=True)
