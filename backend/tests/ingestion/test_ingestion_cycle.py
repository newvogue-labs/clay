from datetime import UTC, datetime
from typing import Any

import pytest

from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.ingestion.context.connectors.demo_news import DemoNewsConnector
from clay.ingestion.context.connectors.demo_sentiment import DemoSentimentConnector
from clay.ingestion.context.manager import ContextConnectorManager
from clay.ingestion.market.exchange_config import ExchangeConfig
from clay.ingestion.market.models import NormalizedMarketBar
from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import IngestionCycleService


def _market_service(client: Any, settings: Any) -> MarketIngestionService:
    cfg = ExchangeConfig(
        exchange_id="test", source=getattr(client, "source", "test"),
        enabled=True, base_url="http://fake",
        symbols=settings.market_symbols, timeframes=settings.market_timeframes,
    )
    return MarketIngestionService({"test": (client, cfg)})


def _make_bar(
    symbol: str = "BTCUSDT",
    timeframe: str = "5m",
    close: float = 70390.20,
) -> NormalizedMarketBar:
    return NormalizedMarketBar(
        symbol=symbol,
        timeframe=timeframe,
        open=70250.10,
        high=70420.00,
        low=70180.40,
        close=close,
        volume=123.45,
        quote_volume=8670000.10,
        source="binance_spot",
        bar_open_time=datetime(2024, 4, 1, 7, 0, tzinfo=UTC),
        bar_close_time=datetime(2024, 4, 1, 7, 14, 59, 999000, tzinfo=UTC),
    )


class FakeBinanceClient:
    source: str = "test"

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200):
        del limit
        return [_make_bar(symbol=symbol, timeframe=interval)]

    def set_http_client(self, client: object | None) -> None:
        return


class FlakyBinanceClient:
    source: str = "test"

    def __init__(self) -> None:
        self.calls: dict[tuple[str, str], int] = {}

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200):
        del limit
        key = (symbol, interval)
        self.calls[key] = self.calls.get(key, 0) + 1
        if key == ("BTCUSDT", "5m") and self.calls[key] == 1:
            raise TimeoutError()
        return [_make_bar(symbol=symbol, timeframe=interval)]

    def set_http_client(self, client: object | None) -> None:
        return


class EmptyErrorBinanceClient:
    source: str = "test"

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200):
        del symbol, interval, limit
        raise TimeoutError()

    def set_http_client(self, client: object | None) -> None:
        return


@pytest.mark.anyio
async def test_ingestion_cycle_persists_market_context_and_ops_records(
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

    summary = await service.run_once(emit=False)

    with sqlite_session_factory() as session:
        market_repository = MarketRepository(session)
        context_repository = ContextRepository(session)
        ops_repository = OpsRepository(session)

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
    sqlite_session_factory,
    sqlite_settings,
) -> None:
    sqlite_settings.market_fetch_retry_delay_seconds = 0.0
    flaky_client = FlakyBinanceClient()
    service = IngestionCycleService(
        settings=sqlite_settings,
        market_service=_market_service(flaky_client, sqlite_settings),
        context_manager=ContextConnectorManager(
            [DemoNewsConnector(), DemoSentimentConnector()],
        ),
        session_factory=sqlite_session_factory,
    )

    summary = await service.run_once(emit=False)

    assert summary.market_records_written == 4
    assert summary.incidents == []
    assert flaky_client.calls[("BTCUSDT", "5m")] == 2

    with sqlite_session_factory() as session:
        ops_repository = OpsRepository(session)
        assert ops_repository.latest_incidents() == []


@pytest.mark.anyio
async def test_ingestion_cycle_uses_exception_class_when_message_is_empty(
    sqlite_session_factory,
    sqlite_settings,
) -> None:
    sqlite_settings.market_symbols = ["BTCUSDT"]
    sqlite_settings.market_timeframes = ["5m"]
    sqlite_settings.market_fetch_retry_delay_seconds = 0.0
    service = IngestionCycleService(
        settings=sqlite_settings,
        market_service=_market_service(EmptyErrorBinanceClient(), sqlite_settings),
        context_manager=ContextConnectorManager([]),
        session_factory=sqlite_session_factory,
    )

    summary = await service.run_once(emit=False)

    assert summary.market_records_written == 0
    assert summary.incidents[0]["message"] == "TimeoutError"

    with sqlite_session_factory() as session:
        ops_repository = OpsRepository(session)
        incidents = ops_repository.latest_incidents()
        freshness_rows = MarketRepository(session).list_freshness_statuses()
        assert incidents[0].message == "TimeoutError"
        assert freshness_rows[0].freshness_state == "unknown"


@pytest.mark.anyio
async def test_ingestion_cycle_resolves_previous_market_incident_after_success(
    sqlite_session_factory,
    sqlite_settings,
) -> None:
    sqlite_settings.market_symbols = ["BTCUSDT"]
    sqlite_settings.market_timeframes = ["5m"]
    sqlite_settings.market_fetch_retry_delay_seconds = 0.0

    client = FakeBinanceClient()
    with sqlite_session_factory() as seed_session:
        ops_repository = OpsRepository(seed_session)
        observed_at = datetime.now(UTC)
        ops_repository.record_source_health_event(
            source_name=f"{client.source}:BTCUSDT:5m",
            severity="error",
            message="TimeoutError",
            recorded_at=observed_at,
        )
        seed_session.commit()

    service = IngestionCycleService(
        settings=sqlite_settings,
        market_service=_market_service(client, sqlite_settings),
        context_manager=ContextConnectorManager([]),
        session_factory=sqlite_session_factory,
    )

    summary = await service.run_once(emit=False)

    with sqlite_session_factory() as session:
        ops_repository = OpsRepository(session)
        resolved = ops_repository.latest_incidents(active_only=False)[0]

        assert summary.market_records_written == 1
        assert ops_repository.latest_incidents() == []
        assert resolved.lifecycle_status == "resolved"
        assert resolved.resolution_message == "Market ingest recovered after successful refresh."
