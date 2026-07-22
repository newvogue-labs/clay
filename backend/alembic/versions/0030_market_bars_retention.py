"""market_bars retention: native TimescaleDB retention policy (D-13 #3)

Revision ID: 0030_market_bars_retention
Revises: 0029_market_bars_compression
Create Date: 2026-07-22

Add a native TimescaleDB retention policy on ``market.market_bars``
that drops chunks older than 730 days.  The policy is created in a
DISABLED state (``scheduled => false``) — no chunks are dropped until
the operator explicitly enables it.

SQLite-guard: upgrade/downgrade are no-ops on SQLite (CI safety).
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0030_market_bars_retention"
down_revision: str | None = "0029_market_bars_compression"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    # Create the retention policy (disabled by default).
    op.execute(
        "SELECT add_retention_policy("
        "  'market.market_bars',"
        "  drop_after => INTERVAL '730 days',"
        "  if_not_exists => TRUE"
        ")"
    )
    # Disable the policy immediately — default-OFF, operator must
    # explicitly enable via ``SELECT alter_job(job_id, scheduled => true)``.
    op.execute(
        "SELECT alter_job(job_id, scheduled => false) "
        "FROM timescaledb_information.jobs "
        "WHERE proc_name = 'policy_retention' "
        "  AND hypertable_schema = 'market' "
        "  AND hypertable_name = 'market_bars'"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    op.execute(
        "SELECT remove_retention_policy(  'market.market_bars',  if_exists => TRUE)"
    )
