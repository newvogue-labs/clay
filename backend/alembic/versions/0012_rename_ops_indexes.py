"""rename ops indexes to no-schema naming convention (G2.5b)

Brings the four ops-scheme secondary indexes in line with the new
``ix_%(table_name)s_%(column_0_name)s`` convention adopted in
``backend/src/clay/db/base.py``. RENAME is metadata-only, instant, and
transactional — no CONCURRENTLY, no reindexing, no data loss.

Revision ID: 0012_rename_ops_indexes
Revises: 0011_ops_retention_indexes
Create Date: 2026-06-06 17:07:50.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0012_rename_ops_indexes"
down_revision: Union[str, None] = "0011_ops_retention_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (schema, old_name, new_name)
_RENAMES = [
    ("ops", "ix_ops_connector_status_history_observed_at", "ix_connector_status_history_observed_at"),
    ("ops", "ix_ops_ingest_runs_started_at", "ix_ingest_runs_started_at"),
    ("ops", "ix_ops_source_health_events_lifecycle_status", "ix_source_health_events_lifecycle_status"),
    ("ops", "ix_ops_source_health_events_recorded_at", "ix_source_health_events_recorded_at"),
]


def upgrade() -> None:
    for schema, old, new in _RENAMES:
        op.execute(f"ALTER INDEX IF EXISTS {schema}.{old} RENAME TO {new}")


def downgrade() -> None:
    for schema, old, new in _RENAMES:
        op.execute(f"ALTER INDEX IF EXISTS {schema}.{new} RENAME TO {old}")
