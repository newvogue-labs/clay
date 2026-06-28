from sqlalchemy.orm import sessionmaker

from clay.db.models_demo import DemoTradeRecord
from clay.db.models_knowledge import KnowledgeChunk, KnowledgeItem
from clay.db.models_context import NewsItem, SentimentSnapshot
from clay.db.models_market import MarketBar, MarketFreshnessStatus, OrderBookSummary
from clay.db.models_ops import ConnectorStatusHistory, IngestRun, SourceHealthEvent
from clay.db.models_review import SignalFeedback
from clay.db.models_validation import ActivationReview, ValidationRun
from clay.db.session import build_engine, build_session_factory
from clay.settings.ingestion import IngestionSettings


def test_ingestion_settings_expose_v1_timeframes() -> None:
    settings = IngestionSettings()

    assert settings.market_timeframes == ["5m", "15m", "1h"]
    assert settings.market_symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert settings.binance_spot_enabled is True
    assert settings.binance_base_url == "https://api.binance.com"


def test_database_bootstrap_uses_configured_url() -> None:
    settings = IngestionSettings(
        database_url="postgresql+psycopg://clay:clay@localhost:5432/clay_test",
    )

    engine = build_engine(settings)
    session_factory = build_session_factory(settings)

    assert engine.url.render_as_string(hide_password=False).endswith("/clay_test")
    assert isinstance(session_factory, sessionmaker)


def test_market_schema_contains_expected_tables() -> None:
    assert MarketBar.__tablename__ == "market_bars"
    assert OrderBookSummary.__tablename__ == "orderbook_summaries"
    assert MarketFreshnessStatus.__tablename__ == "market_freshness_status"


def test_timescale_partition_columns_are_part_of_market_primary_keys() -> None:
    market_bar_primary_key = {
        column.name for column in MarketBar.__table__.primary_key.columns
    }
    orderbook_primary_key = {
        column.name for column in OrderBookSummary.__table__.primary_key.columns
    }

    assert market_bar_primary_key == {"id", "bar_open_time"}
    assert orderbook_primary_key == {"id", "captured_at"}
    assert MarketBar.__table__.c.id.identity is not None
    assert OrderBookSummary.__table__.c.id.identity is not None


def test_context_schema_contains_expected_tables() -> None:
    assert NewsItem.__tablename__ == "news_items"
    assert SentimentSnapshot.__tablename__ == "sentiment_snapshots"


def test_ops_schema_contains_expected_tables() -> None:
    assert IngestRun.__tablename__ == "ingest_runs"
    assert ConnectorStatusHistory.__tablename__ == "connector_status_history"
    assert SourceHealthEvent.__tablename__ == "source_health_events"
    assert "lifecycle_status" in SourceHealthEvent.__table__.c
    assert "resolved_at" in SourceHealthEvent.__table__.c


def test_demo_schema_contains_expected_tables() -> None:
    assert DemoTradeRecord.__tablename__ == "demo_trade_records"
    assert "executed_symbol" in DemoTradeRecord.__table__.c


def test_review_schema_contains_expected_tables() -> None:
    assert SignalFeedback.__tablename__ == "signal_feedback"
    assert "feedback_label" in SignalFeedback.__table__.c


def test_knowledge_schema_contains_expected_tables() -> None:
    assert KnowledgeItem.__tablename__ == "knowledge_items"
    assert KnowledgeChunk.__tablename__ == "knowledge_chunks"


def test_validation_schema_contains_expected_tables() -> None:
    assert ValidationRun.__tablename__ == "validation_runs"
    assert ActivationReview.__tablename__ == "activation_reviews"
