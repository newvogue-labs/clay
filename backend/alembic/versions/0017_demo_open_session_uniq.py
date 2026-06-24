"""add partial unique index: one open record per session (FIX-DEDUP-1)

Revision ID: 0017_demo_open_session_uniq
Revises: 0016_provider_pool
Create Date: 2026-06-22

Создаёт partial UNIQUE index на demo.demo_trade_records (session_id)
WHERE broker_status = 'awaiting_result' — гарантирует не более одной
открытой записи на сессию на уровне БД.
"""
from collections.abc import Sequence

from alembic import op


revision: str = "0017_demo_open_session_uniq"
down_revision: str | None = "0016_provider_pool"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_demo_open_session "
        "ON demo.demo_trade_records (session_id) "
        "WHERE broker_status = 'awaiting_result'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS demo.uq_demo_open_session")
