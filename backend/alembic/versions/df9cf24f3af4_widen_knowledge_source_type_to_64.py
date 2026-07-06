"""widen_knowledge_source_type_to_64

Revision ID: df9cf24f3af4
Revises: 0021_execution_overrides
Create Date: 2026-07-05 21:08:14.656761
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "df9cf24f3af4"
down_revision: Union[str, None] = "0021_execution_overrides"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "knowledge_items",
        "source_type",
        type_=sa.String(64),
        schema="knowledge",
    )


def downgrade() -> None:
    op.alter_column(
        "knowledge_items",
        "source_type",
        type_=sa.String(32),
        schema="knowledge",
    )
