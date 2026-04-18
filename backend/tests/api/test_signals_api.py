import asyncio
from datetime import UTC, datetime, timedelta

from clay.api.routes.signals import get_signal_overview
from clay.bootstrap import signal_engine_service
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository


def seed_signal_api_data(session) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(session)
    context_repository = ContextRepository(session)
    ops_repository = OpsRepository(session)
    market_repository.upsert_market_bars(
        [
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "open": 70200.0,
                "high": 70620.0,
                "low": 70020.0,
                "close": 70540.0,
                "volume": 260.0,
                "quote_volume": 18300000.0,
                "source": "binance_spot",
                "bar_open_time": now - timedelta(minutes=15),
                "bar_close_time": now - timedelta(minutes=1),
            },
        ]
    )
    market_repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        freshness_state="fresh",
        evaluated_at=now,
        latest_bar_open_time=now - timedelta(minutes=15),
        is_stale=False,
    )
    context_repository.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "BTC keeps leadership",
                "summary": "Momentum stays constructive.",
                "published_at": now - timedelta(minutes=30),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/btc",
            },
        ]
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.76,
                "captured_at": now - timedelta(minutes=20),
            },
        ]
    )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    session.commit()


def test_signal_overview_route_returns_evaluated_signals(db_session) -> None:
    seed_signal_api_data(db_session)

    payload = asyncio.run(get_signal_overview(db_session, signal_engine_service))

    assert payload["signals"]
    assert payload["signals"][0]["response_action"] in {
        "warning_only",
        "lower_confidence",
        "switch_to_defensive",
        "block_signal",
    }
