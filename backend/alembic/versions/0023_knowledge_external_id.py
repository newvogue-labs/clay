"""add external_id to knowledge_items for idempotent vault sync

Revision ID: 0023_knowledge_external_id
Revises: df9cf24f3af4
Create Date: 2026-07-06 17:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0023_knowledge_external_id"
down_revision: Union[str, None] = "df9cf24f3af4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_items",
        sa.Column("external_id", sa.String(255), nullable=True),
        schema="knowledge",
    )
    op.create_index(
        "uq_knowledge_items_external_id",
        "knowledge_items",
        ["external_id"],
        unique=True,
        schema="knowledge",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_knowledge_items_external_id",
        table_name="knowledge_items",
        schema="knowledge",
    )
    op.drop_column("knowledge_items", "external_id", schema="knowledge")
