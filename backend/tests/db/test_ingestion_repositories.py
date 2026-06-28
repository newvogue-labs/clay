from datetime import UTC, datetime

from sqlalchemy import func, select

from clay.db.models_market import MarketBar, MarketFreshnessStatus
from clay.db.repositories_context import ContextRepository
import pytest

from clay.db.repositories_market import MarketRepository, set_source_priority
from clay.db.repositories_ops import OpsRepository


def test_source_unique_constraint_allows_different_sources(db_session) -> None:
    """E2: source is part of UC — rows with same (symbol,timeframe,bar_open_time)
    but different source coexist (multi-exchange readiness)."""
    repository = MarketRepository(db_session)
    observed_at = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)

    # Bar from Binance
    written_1 = repository.upsert_market_bars(
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
        ]
    )

    # Bar with same key but different source (e.g. Bybit)
    written_2 = repository.upsert_market_bars(
        [
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "open": 70210.0,
                "high": 70410.0,
                "low": 70120.0,
                "close": 70360.0,
                "volume": 130.0,
                "quote_volume": 8550000.0,
                "source": "bybit_spot",
                "bar_open_time": observed_at,
                "bar_close_time": observed_at,
            },
        ]
    )
    db_session.commit()

    assert written_1 == (1, 0)
    assert written_2 == (1, 0)

    count = db_session.scalar(select(func.count(MarketBar.id)))
    assert count == 2  # both rows coexist


def test_freshness_status_stores_source(db_session) -> None:
    """E2: freshness_status carries source on both success and failure paths."""
    repository = MarketRepository(db_session)
    observed_at = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)

    repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        source="binance_spot",
        freshness_state="fresh",
        evaluated_at=observed_at,
        latest_bar_open_time=observed_at,
        is_stale=False,
    )
    repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        source="bybit_spot",
        freshness_state="unknown",
        evaluated_at=observed_at,
        latest_bar_open_time=None,
        is_stale=True,
    )
    db_session.commit()

    rows = db_session.scalars(select(MarketFreshnessStatus)).all()
    assert len(rows) == 2
    assert {r.source for r in rows} == {"binance_spot", "bybit_spot"}
    assert rows[0].freshness_state in ("fresh", "unknown")


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
        source="binance_spot",
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
    assert (
        recent[0].resolution_message
        == "Market ingest recovered after successful refresh."
    )


def _create_bar(symbol: str, timeframe: str, close_time: datetime, source: str) -> dict:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "open": 70000.0,
        "high": 70100.0,
        "low": 69900.0,
        "close": 70050.0,
        "volume": 100.0,
        "quote_volume": 7005000.0,
        "source": source,
        "bar_open_time": datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
        "bar_close_time": close_time,
    }


@pytest.fixture(autouse=True)
def _reset_source_priority() -> ...:
    yield
    set_source_priority(None)


def test_list_latest_bars_preferred_source_wins(db_session) -> None:
    """Given priority [binance, bybit], binance bar wins even if bybit is fresher."""
    set_source_priority(["binance_spot", "bybit_spot"])
    repository = MarketRepository(db_session)

    t1 = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 4, 16, 10, 5, tzinfo=UTC)

    repository.upsert_market_bars(
        [
            _create_bar("BTCUSDT", "5m", close_time=t1, source="binance_spot"),
            _create_bar("BTCUSDT", "5m", close_time=t2, source="bybit_spot"),
        ]
    )
    db_session.commit()

    result = repository.list_latest_bars(limit=5)
    assert len(result) == 1
    assert result[0].source == "binance_spot"  # older binance wins over newer bybit


def test_list_latest_bars_fallback_when_preferred_absent(db_session) -> None:
    """No binance bar → bybit bar returned (fallback)."""
    set_source_priority(["binance_spot", "bybit_spot"])
    repository = MarketRepository(db_session)

    t = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)
    repository.upsert_market_bars(
        [
            _create_bar("BTCUSDT", "5m", close_time=t, source="bybit_spot"),
        ]
    )
    db_session.commit()

    result = repository.list_latest_bars(limit=5)
    assert len(result) == 1
    assert result[0].source == "bybit_spot"


def test_list_latest_bars_priority_swap(db_session) -> None:
    """Swapped priority returns bybit bar."""
    set_source_priority(["bybit_spot", "binance_spot"])
    repository = MarketRepository(db_session)

    t1 = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 4, 16, 10, 5, tzinfo=UTC)

    repository.upsert_market_bars(
        [
            _create_bar("BTCUSDT", "5m", close_time=t2, source="bybit_spot"),
            _create_bar("BTCUSDT", "5m", close_time=t1, source="binance_spot"),
        ]
    )
    db_session.commit()

    result = repository.list_latest_bars(limit=5)
    assert len(result) == 1
    assert result[0].source == "bybit_spot"


def test_list_latest_bars_one_row_per_symbol_timeframe(db_session) -> None:
    """Two sources → still one row per (symbol, timeframe)."""
    set_source_priority(["binance_spot", "bybit_spot"])
    repository = MarketRepository(db_session)

    t = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)
    repository.upsert_market_bars(
        [
            _create_bar("BTCUSDT", "5m", close_time=t, source="binance_spot"),
            _create_bar("BTCUSDT", "5m", close_time=t, source="bybit_spot"),
            _create_bar("ETHUSDT", "15m", close_time=t, source="binance_spot"),
        ]
    )
    db_session.commit()

    result = repository.list_latest_bars(limit=5)
    assert len(result) == 2  # BTCUSDT 5m + ETHUSDT 15m
    assert {b.symbol for b in result} == {"BTCUSDT", "ETHUSDT"}


def test_list_latest_bars_unknown_source_lowest_priority(db_session) -> None:
    """Unknown source sorts to end — known-preferred wins."""
    set_source_priority(["binance_spot"])
    repository = MarketRepository(db_session)

    t = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)
    repository.upsert_market_bars(
        [
            _create_bar("BTCUSDT", "5m", close_time=t, source="unknown_source"),
            _create_bar("BTCUSDT", "5m", close_time=t, source="binance_spot"),
        ]
    )
    db_session.commit()

    result = repository.list_latest_bars(limit=5)
    assert len(result) == 1
    assert result[0].source == "binance_spot"


def test_list_freshness_preferred_wins_even_if_stale(db_session) -> None:
    """Preferred source freshness returned even when stale; bybit fresh ignored."""
    set_source_priority(["binance_spot", "bybit_spot"])
    repository = MarketRepository(db_session)
    t = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)

    repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="5m",
        source="bybit_spot",
        freshness_state="fresh",
        evaluated_at=t,
        latest_bar_open_time=t,
        is_stale=False,
    )
    repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="5m",
        source="binance_spot",
        freshness_state="stale",
        evaluated_at=t,
        latest_bar_open_time=t,
        is_stale=True,
    )
    db_session.commit()

    rows = repository.list_freshness_statuses()
    assert len(rows) == 1
    assert rows[0].source == "binance_spot"
    assert rows[0].freshness_state == "stale"


def test_list_freshness_fallback_when_preferred_missing(db_session) -> None:
    """No binance freshness → bybit returned."""
    set_source_priority(["binance_spot", "bybit_spot"])
    repository = MarketRepository(db_session)
    t = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)

    repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="5m",
        source="bybit_spot",
        freshness_state="fresh",
        evaluated_at=t,
        latest_bar_open_time=t,
        is_stale=False,
    )
    db_session.commit()

    rows = repository.list_freshness_statuses()
    assert len(rows) == 1
    assert rows[0].source == "bybit_spot"


def test_list_latest_bars_binance_only_byte_identical(db_session) -> None:
    """Single source with default priority → same result as before."""
    repository = MarketRepository(db_session)
    observed_at = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)

    repository.upsert_market_bars(
        [
            _create_bar("BTCUSDT", "5m", close_time=observed_at, source="binance_spot"),
        ]
    )
    repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="5m",
        source="binance_spot",
        freshness_state="fresh",
        evaluated_at=observed_at,
        latest_bar_open_time=observed_at,
        is_stale=False,
    )
    db_session.commit()

    bars = repository.list_latest_bars()
    freshness = repository.list_freshness_statuses()

    assert len(bars) == 1
    assert bars[0].source == "binance_spot"
    assert len(freshness) == 1
    assert freshness[0].source == "binance_spot"


def test_source_priority_extracted_from_exchange_config_source_field(
    db_session,
) -> None:
    """Pin: bootstrap extracts priority from ``cfg.source``, not ``exchange_id`` or dict key.

    If ``exchange_id != source`` (future E5), priority must still work.
    This test emulates the bootstrap path: ``[cfg.source for cfg in exchanges_map.values()]``.
    """
    from clay.ingestion.market.exchange_config import ExchangeConfig

    exchanges = {
        "bybit_exchange": ExchangeConfig(
            exchange_id="bybit_exchange",
            source="bybit_spot",
            enabled=True,
            base_url="https://api.bybit.com",
        ),
        "binance_exchange": ExchangeConfig(
            exchange_id="binance_exchange",
            source="binance_spot",
            enabled=True,
            base_url="https://api.binance.com",
        ),
    }
    source_priority = [cfg.source for cfg in exchanges.values()]
    assert source_priority == ["bybit_spot", "binance_spot"]

    set_source_priority(source_priority)
    repository = MarketRepository(db_session)

    t1 = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 4, 16, 10, 5, tzinfo=UTC)

    repository.upsert_market_bars(
        [
            _create_bar("BTCUSDT", "5m", close_time=t2, source="binance_spot"),
            _create_bar("BTCUSDT", "5m", close_time=t1, source="bybit_spot"),
        ]
    )
    db_session.commit()

    result = repository.list_latest_bars(limit=5)
    assert len(result) == 1
    assert (
        result[0].source == "bybit_spot"
    )  # bybit preferred, older bybit wins over newer binance
