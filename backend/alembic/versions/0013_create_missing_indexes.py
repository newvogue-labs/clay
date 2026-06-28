"""create 45 missing non-hypertable indexes concurrently (G2.5c wave 1)

Closes the model-to-DB drift for non-hypertable tables by materialising
the 45 indexes already declared on the ORM models but absent in the
live database. Each CREATE INDEX runs CONCURRENTLY (no exclusive lock)
and is idempotent (if_not_exists). Downgrade drops them symmetrically.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0013_create_missing_indexes"
down_revision: Union[str, None] = "0012_rename_ops_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (schema, table, index_name, [columns]) -- NO-SCHEMA convention ix_<table>_<col>
_INDEXES: list[tuple[str, str, str, list[str]]] = [
    # context (6)
    ("context", "news_items", "ix_news_items_published_at", ["published_at"]),
    ("context", "news_items", "ix_news_items_source_name", ["source_name"]),
    ("context", "news_items", "ix_news_items_symbol", ["symbol"]),
    (
        "context",
        "sentiment_snapshots",
        "ix_sentiment_snapshots_captured_at",
        ["captured_at"],
    ),
    (
        "context",
        "sentiment_snapshots",
        "ix_sentiment_snapshots_source_name",
        ["source_name"],
    ),
    ("context", "sentiment_snapshots", "ix_sentiment_snapshots_symbol", ["symbol"]),
    # knowledge (8)
    ("knowledge", "knowledge_chunks", "ix_knowledge_chunks_chunk_type", ["chunk_type"]),
    ("knowledge", "knowledge_chunks", "ix_knowledge_chunks_item_id", ["item_id"]),
    ("knowledge", "knowledge_items", "ix_knowledge_items_category", ["category"]),
    ("knowledge", "knowledge_items", "ix_knowledge_items_created_at", ["created_at"]),
    ("knowledge", "knowledge_items", "ix_knowledge_items_priority", ["priority"]),
    ("knowledge", "knowledge_items", "ix_knowledge_items_source_type", ["source_type"]),
    ("knowledge", "knowledge_items", "ix_knowledge_items_title", ["title"]),
    ("knowledge", "knowledge_items", "ix_knowledge_items_updated_at", ["updated_at"]),
    # market non-hypertable (4)
    (
        "market",
        "market_freshness_status",
        "ix_market_freshness_status_evaluated_at",
        ["evaluated_at"],
    ),
    (
        "market",
        "market_freshness_status",
        "ix_market_freshness_status_freshness_state",
        ["freshness_state"],
    ),
    (
        "market",
        "market_freshness_status",
        "ix_market_freshness_status_symbol",
        ["symbol"],
    ),
    (
        "market",
        "market_freshness_status",
        "ix_market_freshness_status_timeframe",
        ["timeframe"],
    ),
    # ops (8)
    (
        "ops",
        "connector_status_history",
        "ix_connector_status_history_connector_id",
        ["connector_id"],
    ),
    (
        "ops",
        "connector_status_history",
        "ix_connector_status_history_connector_type",
        ["connector_type"],
    ),
    (
        "ops",
        "connector_status_history",
        "ix_connector_status_history_status",
        ["status"],
    ),
    ("ops", "ingest_runs", "ix_ingest_runs_source_name", ["source_name"]),
    ("ops", "ingest_runs", "ix_ingest_runs_source_type", ["source_type"]),
    ("ops", "ingest_runs", "ix_ingest_runs_status", ["status"]),
    ("ops", "source_health_events", "ix_source_health_events_severity", ["severity"]),
    (
        "ops",
        "source_health_events",
        "ix_source_health_events_source_name",
        ["source_name"],
    ),
    # review (9)
    (
        "review",
        "signal_feedback",
        "ix_signal_feedback_confidence_band",
        ["confidence_band"],
    ),
    ("review", "signal_feedback", "ix_signal_feedback_created_at", ["created_at"]),
    (
        "review",
        "signal_feedback",
        "ix_signal_feedback_feedback_label",
        ["feedback_label"],
    ),
    (
        "review",
        "signal_feedback",
        "ix_signal_feedback_model_version",
        ["model_version"],
    ),
    (
        "review",
        "signal_feedback",
        "ix_signal_feedback_outcome_status",
        ["outcome_status"],
    ),
    ("review", "signal_feedback", "ix_signal_feedback_session_id", ["session_id"]),
    ("review", "signal_feedback", "ix_signal_feedback_signal_id", ["signal_id"]),
    (
        "review",
        "signal_feedback",
        "ix_signal_feedback_strategy_mode",
        ["strategy_mode"],
    ),
    ("review", "signal_feedback", "ix_signal_feedback_symbol", ["symbol"]),
    # validation (10)
    (
        "validation",
        "activation_reviews",
        "ix_activation_reviews_created_at",
        ["created_at"],
    ),
    ("validation", "activation_reviews", "ix_activation_reviews_status", ["status"]),
    (
        "validation",
        "activation_reviews",
        "ix_activation_reviews_target_id",
        ["target_id"],
    ),
    (
        "validation",
        "activation_reviews",
        "ix_activation_reviews_target_type",
        ["target_type"],
    ),
    ("validation", "validation_runs", "ix_validation_runs_created_at", ["created_at"]),
    (
        "validation",
        "validation_runs",
        "ix_validation_runs_model_version",
        ["model_version"],
    ),
    ("validation", "validation_runs", "ix_validation_runs_period_end", ["period_end"]),
    (
        "validation",
        "validation_runs",
        "ix_validation_runs_period_start",
        ["period_start"],
    ),
    ("validation", "validation_runs", "ix_validation_runs_run_type", ["run_type"]),
    (
        "validation",
        "validation_runs",
        "ix_validation_runs_strategy_mode",
        ["strategy_mode"],
    ),
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for schema, table, name, cols in _INDEXES:
            op.create_index(
                name,
                table,
                cols,
                schema=schema,
                postgresql_concurrently=True,
                if_not_exists=True,
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for schema, table, name, cols in reversed(_INDEXES):
            op.drop_index(
                name,
                table_name=table,
                schema=schema,
                postgresql_concurrently=True,
                if_exists=True,
            )
