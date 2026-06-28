import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from clay.api.routes.context_data import get_context_summary
from clay.api.routes.ingestion import get_ingestion_health, run_ingestion_cycle
from clay.api.routes.market_data import get_latest_market_bars
from clay.api.routes.shortlist import get_shortlist_metrics
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.settings.ingestion import IngestionSettings
from tests.support.factories import make_ingestion_settings
from clay.ingestion.context.connectors.demo_news import DemoNewsConnector
from clay.ingestion.context.connectors.demo_sentiment import DemoSentimentConnector
from clay.ingestion.context.manager import ContextConnectorManager
from clay.ingestion.market.models import NormalizedMarketBar
from clay.ingestion.market.exchange_config import ExchangeConfig
from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import IngestionCycleService


def _market_service(client: Any, settings: Any) -> MarketIngestionService:
    cfg = ExchangeConfig(
        exchange_id="test",
        source=getattr(client, "source", "test"),
        enabled=True,
        base_url="http://fake",
        symbols=settings.market_symbols,
        timeframes=settings.market_timeframes,
    )
    return MarketIngestionService({"test": (client, cfg)})


def test_ingestion_health_route_returns_market_and_context_sections(
    db_session,
    sqlite_settings,
) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(db_session)
    context_repository = ContextRepository(db_session)
    ops_repository = OpsRepository(db_session)
    market_repository.upsert_market_bars(
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
                "bar_open_time": now - timedelta(minutes=15),
                "bar_close_time": now - timedelta(minutes=1),
            },
        ],
    )
    market_repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        source="binance_spot",
        freshness_state="fresh",
        evaluated_at=now,
        latest_bar_open_time=now - timedelta(minutes=15),
        is_stale=False,
    )
    context_repository.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "BTC holds breakout",
                "summary": "Constructive intraday structure",
                "published_at": now - timedelta(minutes=30),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/btc-breakout",
            },
        ],
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.68,
                "captured_at": now - timedelta(minutes=20),
            },
        ],
    )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    db_session.commit()

    payload = asyncio.run(get_ingestion_health(db_session, sqlite_settings))

    assert "market" in payload
    assert "context" in payload
    assert payload["market"]["items"][0]["symbol"] == "BTCUSDT"
    assert payload["context"]["streams"]["news"] == "fresh"


def test_storage_backed_read_routes_return_seeded_data(
    db_session,
) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(db_session)
    context_repository = ContextRepository(db_session)
    market_repository.upsert_market_bars(
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
                "bar_open_time": now - timedelta(minutes=15),
                "bar_close_time": now - timedelta(minutes=1),
            },
        ],
    )
    market_repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        source="binance_spot",
        freshness_state="fresh",
        evaluated_at=now,
        latest_bar_open_time=now - timedelta(minutes=15),
        is_stale=False,
    )
    context_repository.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "BTC holds breakout",
                "summary": "Constructive intraday structure",
                "published_at": now - timedelta(minutes=30),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/btc-breakout",
            },
        ],
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.68,
                "captured_at": now - timedelta(minutes=20),
            },
        ],
    )
    db_session.commit()

    shortlist_payload = asyncio.run(
        get_shortlist_metrics(
            session=db_session,
            settings=make_ingestion_settings(),
            limit=20,
        ),
    )
    market_payload = asyncio.run(
        get_latest_market_bars(
            db_session,
            symbol=None,
            timeframe=None,
            limit=20,
        ),
    )
    context_payload = asyncio.run(get_context_summary(db_session, limit=5))

    first_row = shortlist_payload["items"][0]
    assert "rolling_volume_score" in first_row
    assert "rolling_volatility_score" in first_row
    assert "availability_status" in first_row
    assert market_payload["items"][0]["symbol"] == "BTCUSDT"
    assert context_payload["news"][0]["headline"] == "BTC holds breakout"


def test_ingestion_health_recomputes_market_staleness_from_latest_bar_time(
    db_session,
    sqlite_settings,
) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(db_session)

    market_repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        source="binance_spot",
        freshness_state="fresh",
        evaluated_at=now - timedelta(days=6),
        latest_bar_open_time=now - timedelta(days=6),
        is_stale=False,
    )
    db_session.commit()

    payload = asyncio.run(get_ingestion_health(db_session, sqlite_settings))

    assert payload["market"]["status"] == "stale"
    assert payload["market"]["blocks_active_trading"] is True
    assert payload["market"]["items"][0]["status"] == "stale"
    assert "delta=6 days" in payload["market"]["items"][0]["reason"]


def test_ingestion_health_tight_threshold_flips_fresh_to_stale(
    db_session,
) -> None:
    tight_settings = IngestionSettings(
        database_url="sqlite+pysqlite://",  # not used, db_session already open
        market_freshness_5m_minutes=1,
        market_freshness_15m_minutes=1,
        market_freshness_1h_minutes=1,
    )
    now = datetime.now(UTC)
    market_repo = MarketRepository(db_session)
    market_repo.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="5m",
        source="binance_spot",
        freshness_state="fresh",
        evaluated_at=now - timedelta(minutes=6),
        latest_bar_open_time=now - timedelta(minutes=6),
        is_stale=False,
    )
    db_session.commit()

    payload = asyncio.run(get_ingestion_health(db_session, tight_settings))

    assert payload["market"]["status"] == "stale"
    assert payload["market"]["blocks_active_trading"] is True
    assert payload["market"]["items"][0]["status"] == "stale"


def test_ingestion_health_context_threshold_flips_fresh_to_degraded(
    db_session,
) -> None:
    tight_settings = IngestionSettings(
        database_url="sqlite+pysqlite://",
        context_freshness_news_hours=0,
        context_freshness_sentiment_hours=0,
    )
    now = datetime.now(UTC)
    context_repo = ContextRepository(db_session)
    context_repo.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "old news",
                "summary": "Published 1 hour ago",
                "published_at": now - timedelta(hours=1),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/old",
            },
        ]
    )
    context_repo.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.68,
                "captured_at": now - timedelta(hours=1),
            },
        ]
    )
    db_session.commit()

    payload = asyncio.run(get_ingestion_health(db_session, tight_settings))

    assert payload["context"]["status"] == "degraded"


class FakeBinanceClient:
    """E1: conforms to ``MarketDataClient`` protocol."""

    source: str = "test"

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200):
        del symbol, interval, limit
        return [
            NormalizedMarketBar(
                symbol="BTCUSDT",
                timeframe="5m",
                open=70250.10,
                high=70420.00,
                low=70180.40,
                close=70390.20,
                volume=123.45,
                quote_volume=8670000.10,
                source="binance_spot",
                bar_open_time=datetime(2024, 4, 1, 7, 0, tzinfo=UTC),
                bar_close_time=datetime(2024, 4, 1, 7, 14, 59, 999000, tzinfo=UTC),
            ),
        ]

    def set_http_client(self, client: object | None) -> None:
        return


def test_ingestion_run_route_executes_storage_backed_cycle(
    sqlite_session_factory,
    sqlite_settings,
) -> None:
    service = IngestionCycleService(
        settings=sqlite_settings,
        market_service=_market_service(FakeBinanceClient(), sqlite_settings),
        context_manager=ContextConnectorManager(
            [DemoNewsConnector(), DemoSentimentConnector()],
        ),
        session_factory=sqlite_session_factory,
    )

    payload = asyncio.run(run_ingestion_cycle(service))

    assert payload["market_records_written"] == 4
    assert payload["news_records_written"] == 1
    assert payload["sentiment_records_written"] == 1
