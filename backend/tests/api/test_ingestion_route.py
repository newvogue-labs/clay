"""Tests for the B5 ``POST /ingestion/run`` route — 409 when busy.

The route contract is unchanged for the happy path: the manual
``run_once(session, emit=True)`` call writes audit + bus, returns
the summary payload. The new contract adds **409 Conflict** when
the ``asyncio.Lock`` is held — the operator-facing equivalent of
the scheduler-job's quiet ``skip + log`` path.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import HTTPException

from clay.api.routes.ingestion import run_ingestion_cycle
from clay.ingestion.context.connectors.demo_news import DemoNewsConnector
from clay.ingestion.context.connectors.demo_sentiment import DemoSentimentConnector
from clay.ingestion.context.manager import ContextConnectorManager
from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import IngestionCycleService
from clay.settings.ingestion import IngestionSettings


class _FakeBinanceClient:
    """Returns a single deterministic kline per call."""

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


def _build_service(sqlite_settings: IngestionSettings) -> IngestionCycleService:
    return IngestionCycleService(
        settings=sqlite_settings,
        market_service=MarketIngestionService(_FakeBinanceClient()),
        context_manager=ContextConnectorManager(
            [DemoNewsConnector(), DemoSentimentConnector()],
        ),
    )


def test_manual_route_409_when_ingestion_running(
    db_session: Any,
    sqlite_settings: IngestionSettings,
) -> None:
    """``POST /ingestion/run`` raises HTTP 409 when the cycle is in flight.

    Simulates the operator double-clicking ``Run cycle`` while the
    previous call has not returned: the second request is rejected
    with ``409 Conflict`` and the message names the cause so the
    operator does not have to read the code to understand why.
    """
    service = _build_service(sqlite_settings)

    # Manually acquire the service's lock to put it in a "busy" state.
    asyncio.run(service._lock.acquire())  # noqa: SLF001 (intentional — test the lock)
    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(run_ingestion_cycle(db_session, service))
        assert exc_info.value.status_code == 409
        assert "already running" in str(exc_info.value.detail)
    finally:
        service._lock.release()  # noqa: SLF001
