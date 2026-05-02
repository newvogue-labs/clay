from datetime import UTC, datetime

import pytest

from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.ingestion.context.connectors.demo_news import DemoNewsConnector
from clay.ingestion.context.connectors.demo_sentiment import DemoSentimentConnector
from clay.ingestion.context.manager import ContextConnectorManager
from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import IngestionCycleService


class FakeBinanceClient:
    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200):
        del symbol, interval, limit
        return [
            [
                1711954800000,
                "70250.10",
                "70420.00",
                "70180.40",
                "70390.20",
                "123.45",
                1711955699999,
                "8670000.10",
            ],
        ]


class FlakyBinanceClient:
    def __init__(self) -> None:
        self.calls: dict[tuple[str, str], int] = {}

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200):
        del limit
        key = (symbol, interval)
        self.calls[key] = self.calls.get(key, 0) + 1
        if key == ("BTCUSDT", "5m") and self.calls[key] == 1:
            raise TimeoutError()
        return [
            [
                1711954800000,
                "70250.10",
                "70420.00",
                "70180.40",
                "70390.20",
                "123.45",
                1711955699999,
                "8670000.10",
            ],
        ]


class EmptyErrorBinanceClient:
    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200):
        del symbol, interval, limit
        raise TimeoutError()


@pytest.mark.anyio
async def test_ingestion_cycle_persists_market_context_and_ops_records(
    db_session,
    sqlite_settings,
) -> None:
    service = IngestionCycleService(
        settings=sqlite_settings,
        market_service=MarketIngestionService(FakeBinanceClient()),
        context_manager=ContextConnectorManager(
            [DemoNewsConnector(), DemoSentimentConnector()],
        ),
    )

    summary = await service.run_once(db_session)

    market_repository = MarketRepository(db_session)
    context_repository = ContextRepository(db_session)
    ops_repository = OpsRepository(db_session)

    assert summary.market_records_written == 4
    assert summary.news_records_written == 1
    assert summary.sentiment_records_written == 1
    assert summary.freshness_updates_written == 4
    assert len(market_repository.list_latest_bars()) == 4
    assert len(market_repository.list_freshness_statuses()) == 4
    assert context_repository.latest_news(limit=1)[0].source_name == "demo_news_feed"
    assert context_repository.latest_sentiment(limit=1)[0].source_name == "demo_sentiment_feed"
    assert len(ops_repository.latest_connector_statuses()) == 2


@pytest.mark.anyio
async def test_ingestion_cycle_retries_transient_market_failures(
    db_session,
    sqlite_settings,
) -> None:
    sqlite_settings.market_fetch_retry_delay_seconds = 0.0
    flaky_client = FlakyBinanceClient()
    service = IngestionCycleService(
        settings=sqlite_settings,
        market_service=MarketIngestionService(flaky_client),
        context_manager=ContextConnectorManager(
            [DemoNewsConnector(), DemoSentimentConnector()],
        ),
    )

    summary = await service.run_once(db_session)
    ops_repository = OpsRepository(db_session)

    assert summary.market_records_written == 4
    assert summary.incidents == []
    assert flaky_client.calls[("BTCUSDT", "5m")] == 2
    assert ops_repository.latest_incidents() == []


@pytest.mark.anyio
async def test_ingestion_cycle_uses_exception_class_when_message_is_empty(
    db_session,
    sqlite_settings,
) -> None:
    sqlite_settings.market_symbols = ["BTCUSDT"]
    sqlite_settings.market_timeframes = ["5m"]
    sqlite_settings.market_fetch_retry_delay_seconds = 0.0
    service = IngestionCycleService(
        settings=sqlite_settings,
        market_service=MarketIngestionService(EmptyErrorBinanceClient()),
        context_manager=ContextConnectorManager([]),
    )

    summary = await service.run_once(db_session)
    ops_repository = OpsRepository(db_session)
    incidents = ops_repository.latest_incidents()
    freshness_rows = MarketRepository(db_session).list_freshness_statuses()

    assert summary.market_records_written == 0
    assert summary.incidents[0]["message"] == "TimeoutError"
    assert incidents[0].message == "TimeoutError"
    assert freshness_rows[0].freshness_state == "unknown"


@pytest.mark.anyio
async def test_ingestion_cycle_resolves_previous_market_incident_after_success(
    db_session,
    sqlite_settings,
) -> None:
    sqlite_settings.market_symbols = ["BTCUSDT"]
    sqlite_settings.market_timeframes = ["5m"]
    sqlite_settings.market_fetch_retry_delay_seconds = 0.0
    ops_repository = OpsRepository(db_session)
    observed_at = datetime.now(UTC)

    ops_repository.record_source_health_event(
        source_name="binance_spot:BTCUSDT:5m",
        severity="error",
        message="TimeoutError",
        recorded_at=observed_at,
    )
    db_session.commit()

    service = IngestionCycleService(
        settings=sqlite_settings,
        market_service=MarketIngestionService(FakeBinanceClient()),
        context_manager=ContextConnectorManager([]),
    )

    summary = await service.run_once(db_session)
    resolved = ops_repository.latest_incidents(active_only=False)[0]

    assert summary.market_records_written == 1
    assert ops_repository.latest_incidents() == []
    assert resolved.lifecycle_status == "resolved"
    assert resolved.resolution_message == "Market ingest recovered after successful refresh."
