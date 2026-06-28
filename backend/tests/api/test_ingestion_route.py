"""Tests for the B5 ``POST /ingestion/run`` route — 409 when busy.

The route contract is unchanged for the happy path: the manual
``run_once(session, emit=True)`` call writes audit + bus, returns
the summary payload. The new contract adds **409 Conflict** when
the ``asyncio.Lock`` is held — the operator-facing equivalent of
the scheduler-job's quiet ``skip + log`` path.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException

from clay.api.routes.ingestion import run_ingestion_cycle
from clay.ingestion.context.connectors.demo_news import DemoNewsConnector
from clay.ingestion.context.connectors.demo_sentiment import DemoSentimentConnector
from clay.ingestion.context.manager import ContextConnectorManager
from clay.ingestion.market.exchange_config import ExchangeConfig
from clay.ingestion.market.models import NormalizedMarketBar
from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import IngestionCycleService
from clay.settings.ingestion import IngestionSettings


class _FakeBinanceClient:
    """Returns a single deterministic kline per call.

    E1: conforms to ``MarketDataClient`` protocol — returns
    ``NormalizedMarketBar`` instead of raw arrays.
    """

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


def _build_service(
    sqlite_settings: IngestionSettings, session_factory: Any
) -> IngestionCycleService:
    client = _FakeBinanceClient()
    exchange_config = ExchangeConfig(
        exchange_id="test",
        source=client.source,
        enabled=True,
        base_url="http://fake",
        symbols=list(sqlite_settings.market_symbols),
        timeframes=list(sqlite_settings.market_timeframes),
    )
    return IngestionCycleService(
        settings=sqlite_settings,
        market_service=MarketIngestionService({"test": (client, exchange_config)}),
        context_manager=ContextConnectorManager(
            [DemoNewsConnector(), DemoSentimentConnector()],
        ),
        session_factory=session_factory,
    )


def test_manual_route_409_when_ingestion_running(
    sqlite_session_factory: Any,
    sqlite_settings: IngestionSettings,
) -> None:
    """``POST /ingestion/run`` raises HTTP 409 when the cycle is in flight.

    Simulates the operator double-clicking ``Run cycle`` while the
    previous call has not returned: the second request is rejected
    with ``409 Conflict`` and the message names the cause so the
    operator does not have to read the code to understand why.

    C3: route no longer takes a ``session`` parameter — the service
    owns the session lifecycle inside ``_persist``.
    """
    service = _build_service(sqlite_settings, sqlite_session_factory)

    # Manually acquire the service's lock to put it in a "busy" state.
    asyncio.run(service._lock.acquire())  # noqa: SLF001 (intentional — test the lock)
    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(run_ingestion_cycle(service))
        assert exc_info.value.status_code == 409
        assert "already running" in str(exc_info.value.detail)
    finally:
        service._lock.release()  # noqa: SLF001
