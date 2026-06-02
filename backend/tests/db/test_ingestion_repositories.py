from datetime import UTC, datetime

from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository


def test_market_repository_persists_bars_and_freshness(db_session) -> None:
    repository = MarketRepository(db_session)
    observed_at = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)

    written = repository.upsert_market_bars(
        [
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "open": 70200.0,
                "high": 70400.0,
                "low": 70100.0,
                "close": 70350.0,
                "volume": 120.0,
                "quote_volume": 8440000.0,
                "source": "binance_spot",
                "bar_open_time": observed_at,
                "bar_close_time": observed_at,
            },
        ],
    )
    repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        freshness_state="fresh",
        evaluated_at=observed_at,
        latest_bar_open_time=observed_at,
        is_stale=False,
    )
    db_session.commit()

    latest = repository.list_latest_bars()
    freshness = repository.list_freshness_statuses()

    assert written == (1, 0)  # B5: (inserted, updated) tuple
    assert latest[0].symbol == "BTCUSDT"
    assert freshness[0].freshness_state == "fresh"


def test_context_and_ops_repositories_store_runtime_records(db_session) -> None:
    context_repository = ContextRepository(db_session)
    ops_repository = OpsRepository(db_session)
    observed_at = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)

    news_written = context_repository.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "BTC holds breakout",
                "summary": "Constructive intraday structure",
                "published_at": observed_at,
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/btc-breakout",
            },
        ],
    )
    sentiment_written = context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.68,
                "captured_at": observed_at,
            },
        ],
    )
    run = ops_repository.create_ingest_run(
        source_name="demo_news_feed",
        source_type="news",
        status="running",
        started_at=observed_at,
    )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=observed_at,
    )
    ops_repository.record_source_health_event(
        source_name="demo_news_feed",
        severity="warning",
        message="rate limited",
        recorded_at=observed_at,
    )
    ops_repository.finalize_ingest_run(
        run,
        status="success",
        finished_at=observed_at,
        details={"payload_count": 1},
    )
    db_session.commit()

    assert news_written == 1
    assert sentiment_written == 1
    assert context_repository.latest_news()[0].headline == "BTC holds breakout"
    assert context_repository.latest_sentiment()[0].sentiment_label == "bullish"
    assert ops_repository.latest_connector_statuses()[0].connector_id == "demo-news"
    assert ops_repository.latest_incidents()[0].message == "rate limited"


def test_ops_repository_resolves_active_incidents(db_session) -> None:
    ops_repository = OpsRepository(db_session)
    observed_at = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)

    ops_repository.record_source_health_event(
        source_name="binance_spot:BTCUSDT:5m",
        severity="error",
        message="TimeoutError",
        recorded_at=observed_at,
    )
    resolved_count = ops_repository.resolve_source_health_events(
        source_name="binance_spot:BTCUSDT:5m",
        resolved_at=observed_at,
        resolution_message="Market ingest recovered after successful refresh.",
    )
    db_session.commit()

    recent = ops_repository.latest_incidents(active_only=False)

    assert resolved_count == 1
    assert ops_repository.latest_incidents() == []
    assert recent[0].lifecycle_status == "resolved"
    assert recent[0].resolution_message == "Market ingest recovered after successful refresh."
