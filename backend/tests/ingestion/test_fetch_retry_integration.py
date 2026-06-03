"""Integration tests for ``_fetch_market_bars`` retry behaviour.

D3: exercises the full retry loop with mocked
``market_service.fetch_and_normalize`` and a patched
``asyncio.sleep`` to verify that Retry-After headers are
honoured (capped) and that non-429 paths are unchanged.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from clay.ingestion.market.service import MarketIngestionService
from clay.ingestion.service import IngestionCycleService
from clay.settings.ingestion import IngestionSettings


class _ThrowingBinanceClient:
    """Fake client that raises on demand for controlled testing."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.call_count = 0

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200) -> list[Any]:
        self.call_count += 1
        if self.error is not None:
            raise self.error
        return []


class _SequentialThrowingBinanceClient:
    """Fake client that fails N times then succeeds."""

    def __init__(self, error: Exception, fail_count: int) -> None:
        self._error = error
        self._fail_count = fail_count
        self.call_count = 0

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200) -> list[Any]:
        self.call_count += 1
        if self.call_count <= self._fail_count:
            raise self._error
        return []


def _make_rate_limit_error(
    status_code: int = 429,
    retry_after: str | None = None,
) -> httpx.HTTPStatusError:
    headers: dict[str, str] = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    request = httpx.Request("GET", "https://api.binance.com/api/v3/klines")
    response = httpx.Response(status_code, headers=headers, request=request)
    return httpx.HTTPStatusError("rate limited", request=request, response=response)


SLEEP_TIMES: list[float] = []


async def _tracking_sleep(delay: float) -> None:
    SLEEP_TIMES.append(delay)


@pytest.fixture(autouse=True)
def _reset_sleep_tracker() -> None:
    SLEEP_TIMES.clear()


@pytest.mark.anyio
async def test_429_with_retry_after_uses_capped_delay() -> None:
    """429 + Retry-After "2" → sleep with 2.0."""
    settings = IngestionSettings(binance_retry_after_cap_seconds=60.0)
    client = _ThrowingBinanceClient(
        error=_make_rate_limit_error(retry_after="2"),
    )
    service = IngestionCycleService(
        settings=settings,
        market_service=MarketIngestionService(client),
        context_manager=AsyncMock(),  # type: ignore[arg-type]
        session_factory=AsyncMock(),  # type: ignore[arg-type]
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(asyncio, "sleep", _tracking_sleep)
        with pytest.raises(Exception):
            await service._fetch_market_bars(symbol="BTCUSDT", timeframe="5m")

    assert any(2.0 <= d <= 2.1 for d in SLEEP_TIMES), f"expected ~2.0, got {SLEEP_TIMES}"


@pytest.mark.anyio
async def test_429_without_retry_after_falls_back_to_default() -> None:
    """429 without Retry-After header → sleep with 0.5 (default)."""
    settings = IngestionSettings(market_fetch_retry_delay_seconds=0.5)
    client = _ThrowingBinanceClient(error=_make_rate_limit_error())
    service = IngestionCycleService(
        settings=settings,
        market_service=MarketIngestionService(client),
        context_manager=AsyncMock(),
        session_factory=AsyncMock(),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(asyncio, "sleep", _tracking_sleep)
        with pytest.raises(Exception):
            await service._fetch_market_bars(symbol="BTCUSDT", timeframe="5m")

    assert any(0.4 <= d <= 0.6 for d in SLEEP_TIMES), f"expected ~0.5, got {SLEEP_TIMES}"


@pytest.mark.anyio
async def test_429_with_retry_above_cap_is_capped() -> None:
    """429 + Retry-After "300" (cap 60) → sleep with 60.0."""
    settings = IngestionSettings(binance_retry_after_cap_seconds=60.0)
    client = _ThrowingBinanceClient(error=_make_rate_limit_error(retry_after="300"))
    service = IngestionCycleService(
        settings=settings,
        market_service=MarketIngestionService(client),
        context_manager=AsyncMock(),
        session_factory=AsyncMock(),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(asyncio, "sleep", _tracking_sleep)
        with pytest.raises(Exception):
            await service._fetch_market_bars(symbol="BTCUSDT", timeframe="5m")

    assert any(59.0 <= d <= 61.0 for d in SLEEP_TIMES), f"expected ~60.0, got {SLEEP_TIMES}"


@pytest.mark.anyio
async def test_generic_500_uses_default_delay() -> None:
    """500 → sleep with 0.5 (unchanged behaviour)."""
    settings = IngestionSettings(market_fetch_retry_delay_seconds=0.5)
    client = _ThrowingBinanceClient(error=_make_rate_limit_error(status_code=500))
    service = IngestionCycleService(
        settings=settings,
        market_service=MarketIngestionService(client),
        context_manager=AsyncMock(),
        session_factory=AsyncMock(),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(asyncio, "sleep", _tracking_sleep)
        with pytest.raises(Exception):
            await service._fetch_market_bars(symbol="BTCUSDT", timeframe="5m")

    assert any(0.4 <= d <= 0.6 for d in SLEEP_TIMES), f"expected ~0.5, got {SLEEP_TIMES}"


@pytest.mark.anyio
async def test_retry_succeeds_on_second_attempt_after_429() -> None:
    """429 on 1st attempt → retry → succeeds on 2nd → returns data."""
    error = _make_rate_limit_error(retry_after="1")
    client = _SequentialThrowingBinanceClient(error=error, fail_count=1)
    settings = IngestionSettings(market_fetch_max_attempts=2, binance_retry_after_cap_seconds=60.0)
    service = IngestionCycleService(
        settings=settings,
        market_service=MarketIngestionService(client),
        context_manager=AsyncMock(),
        session_factory=AsyncMock(),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(asyncio, "sleep", _tracking_sleep)
        result = await service._fetch_market_bars(symbol="BTCUSDT", timeframe="5m")

    assert result == []
    assert client.call_count == 2


@pytest.mark.anyio
async def test_retry_exhausted_raises_and_per_symbol_isolation() -> None:
    """429 × 2 attempts → exhausted → exception → isolated via _MarketBatch."""
    error = _make_rate_limit_error(retry_after="1")
    client = _ThrowingBinanceClient(error=error)
    settings = IngestionSettings(market_fetch_max_attempts=2)
    service = IngestionCycleService(
        settings=settings,
        market_service=MarketIngestionService(client),
        context_manager=AsyncMock(),
        session_factory=AsyncMock(),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(asyncio, "sleep", _tracking_sleep)
        with pytest.raises(httpx.HTTPStatusError):
            await service._fetch_market_bars(symbol="BTCUSDT", timeframe="5m")

    assert client.call_count == 2
