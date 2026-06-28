"""add context dedup unique constraints

Revision ID: 0009_context_unique_dedup
Revises: 0008_ops_runtime_state
Create Date: 2026-06-03 12:00:00.000000

Adds DB-level UniqueConstraint on (source_name, headline, published_at) for
context.news_items and (source_name, symbol, captured_at) for
context.sentiment_snapshots. This is defense-in-depth on top of the
app-level SELECT-skip dedup in ContextRepository — closing the TOCTOU
window between SELECT and INSERT under multi-worker or restart races.

The defensive dedup-cleanup step (DELETE ... USING ...) runs FIRST so the
ADD CONSTRAINT succeeds even if duplicates already exist. It is idempotent
(no-op on a clean DB) and PG-specific by design — migrations are not
exercised on SQLite per the A1 test policy.
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0009_context_unique_dedup"
down_revision: str | None = "0008_ops_runtime_state"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. Defensive dedup-cleanup for news_items: keep MIN(id) per dedup key.
    # PG-only syntax (USING self-join). Migrations are PG-only by A1 policy;
    # SQLite tests use Base.metadata.create_all and never run this migration.
    op.execute(
        """
        DELETE FROM context.news_items AS n
        USING context.news_items AS n2
        WHERE n.id > n2.id
          AND n.source_name = n2.source_name
          AND n.headline = n2.headline
          AND n.published_at = n2.published_at;
        """
    )

    # 2. Defensive dedup-cleanup for sentiment_snapshots.
    op.execute(
        """
        DELETE FROM context.sentiment_snapshots AS s
        USING context.sentiment_snapshots AS s2
        WHERE s.id > s2.id
          AND s.source_name = s2.source_name
          AND s.symbol = s2.symbol
          AND s.captured_at = s2.captured_at;
        """
    )

    # 3. Add UniqueConstraint on news_items.
    op.create_unique_constraint(
        "uq_news_items_dedup",
        "news_items",
        ["source_name", "headline", "published_at"],
        schema="context",
    )

    # 4. Add UniqueConstraint on sentiment_snapshots.
    op.create_unique_constraint(
        "uq_sentiment_snapshots_dedup",
        "sentiment_snapshots",
        ["source_name", "symbol", "captured_at"],
        schema="context",
    )


def downgrade() -> None:
    # Drop constraints. We do NOT restore dedup-cleanup state — data is left
    # as-is (still functional, just without the unique guarantee).
    op.drop_constraint(
        "uq_sentiment_snapshots_dedup",
        "sentiment_snapshots",
        schema="context",
    )
    op.drop_constraint(
        "uq_news_items_dedup",
        "news_items",
        schema="context",
    )
