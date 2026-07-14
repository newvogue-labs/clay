"""add ops.execution_proof_decisions table (S-EXEC-SAFE-2b persistence)

Revision ID: 0024_execution_proof_decisions
Revises: 0023_knowledge_external_id
Create Date: 2026-07-14

INSERT-only audit table for proof-gate admission decisions.
Mirrors the ExecutionOverride pattern: surrogate PK, append-only,
schema="ops".
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0024_execution_proof_decisions"
down_revision: str | None = "0023_knowledge_external_id"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_proof_decisions",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("intent_hash", sa.String(16), nullable=False),
        sa.Column("snapshot_hash", sa.String(16), nullable=False),
        sa.Column("snapshot_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_version", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("client_order_id", sa.Text(), nullable=False),
        sa.Column("reason_codes", sa.Text(), nullable=False),
        sa.Column("invariant_results", sa.Text(), nullable=False),
        sa.Column("arming_event_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id", name="pk_execution_proof_decisions"),
        schema="ops",
    )
    op.create_index(
        "ix_execution_proof_decisions_symbol_created_at",
        "execution_proof_decisions",
        ["symbol", "created_at"],
        schema="ops",
    )
    op.create_index(
        "ix_execution_proof_decisions_decision_created_at",
        "execution_proof_decisions",
        ["decision", "created_at"],
        schema="ops",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_execution_proof_decisions_decision_created_at",
        table_name="execution_proof_decisions",
        schema="ops",
    )
    op.drop_index(
        "ix_execution_proof_decisions_symbol_created_at",
        table_name="execution_proof_decisions",
        schema="ops",
    )
    op.drop_table("execution_proof_decisions", schema="ops")
