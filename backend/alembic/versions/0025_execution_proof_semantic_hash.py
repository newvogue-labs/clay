"""add semantic_hash to ops.execution_proof_decisions (D-8 duplicate-intent wiring)

Revision ID: 0025_proof_semantic_hash
Revises: 0024_execution_proof_decisions
Create Date: 2026-07-18

semantic_hash =经济 fingerprint БЕЗ client_order_id (dedup-key, не idempotency-key).
nullable=True: старые строки без значения; новые пишут при persist.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0025_proof_semantic_hash"
down_revision: str | None = "0024_execution_proof_decisions"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "execution_proof_decisions",
        sa.Column("semantic_hash", sa.String(16), nullable=True),
        schema="ops",
    )
    op.create_index(
        "ix_execution_proof_decisions_semantic_hash_created_at",
        "execution_proof_decisions",
        ["semantic_hash", "created_at"],
        schema="ops",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_execution_proof_decisions_semantic_hash_created_at",
        table_name="execution_proof_decisions",
        schema="ops",
    )
    op.drop_column("execution_proof_decisions", "semantic_hash", schema="ops")
