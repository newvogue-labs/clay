"""Tests for ``BinanceSpotClient``.

B4.5 contract pin: this is the first direct test of the binance client
(``MarketIngestionService`` is tested in ``test_ingestion_cycle.py`` via
``FakeBinanceClient``, which short-circuits the HTTP layer). The injected-
client path is the production path (``bootstrap.py`` wires
``BinanceSpotClient`` without injecting a client, but every caller in the
ingestion stack passes through the same ``get -> raise_for_status -> json``
sequence covered here).

E1: ``fetch_klines`` now returns ``list[NormalizedMarketBar]`` —
normalization is internal to the client.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from clay.ingestion.market.binance_client import BinanceSpotClient
from clay.ingestion.market.models import NormalizedMarketBar
from clay.settings.ingestion import IngestionSettings


@pytest.mark.anyio
async def test_fetch_klines_returns_normalized_bars() -> None:
    """E1: ``fetch_klines`` returns ``NormalizedMarketBar`` list (not raw arrays)."""
    raw_kline = [
        1711954800000,
        "70250.10",
        "70420.00",
        "70180.40",
        "70390.20",
        "123.45",
        1711955699999,
        "8670000.10",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/klines"
        return httpx.Response(200, json=[raw_kline])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = BinanceSpotClient(
            base_url="https://test.invalid",
            client=mock_client,
        )

        result = await client.fetch_klines(symbol="BTCUSDT", interval="5m", limit=1)

    assert len(result) == 1
    bar = result[0]
    assert isinstance(bar, NormalizedMarketBar)
    assert bar.symbol == "BTCUSDT"
    assert bar.timeframe == "5m"
    assert bar.open == 70250.10
    assert bar.high == 70420.00
    assert bar.low == 70180.40
    assert bar.close == 70390.20
    assert bar.volume == 123.45
    assert bar.quote_volume == 8670000.10
    assert bar.source == "binance_spot"
    assert bar.bar_open_time == datetime(2024, 4, 1, 7, 0, tzinfo=UTC)
    assert bar.bar_close_time == datetime(2024, 4, 1, 7, 14, 59, 999000, tzinfo=UTC)


@pytest.mark.anyio
async def test_fetch_klines_creates_async_client_per_call_when_none_injected() -> None:
    """C2: else-branch fallback contract (B4.5) — when no client is injected
    via constructor or ``set_http_client``, ``fetch_klines`` builds a new
    ``httpx.AsyncClient`` per call. Pinned for unit-test / script paths
    that bypass the lifespan-owned client.

    E1: still verifies the HTTP path reaches Binance and normalizes.
    """
    raw_kline = [
        1711954800000,
        "70100.00",
        "70200.00",
        "70050.50",
        "70180.20",
        "200.00",
        1711955699999,
        "14000000.00",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/klines"
        return httpx.Response(200, json=[raw_kline])

    # No client=... in constructor, no set_http_client call → else-branch.
    client = BinanceSpotClient(base_url="https://test.invalid")

    # Inject the MockTransport indirectly by patching the AsyncClient
    # class used inside the else-branch.
    import clay.ingestion.market.binance_client as binance_module

    original_async_client = binance_module.httpx.AsyncClient

    class _PatchedAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            self._client = original_async_client(
                transport=httpx.MockTransport(handler), *args, **kwargs
            )

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, *args):
            return await self._client.__aexit__(*args)

    binance_module.httpx.AsyncClient = _PatchedAsyncClient  # type: ignore[assignment]
    try:
        result = await client.fetch_klines(symbol="BTCUSDT", interval="5m", limit=1)
    finally:
        binance_module.httpx.AsyncClient = original_async_client  # type: ignore[assignment]

    assert len(result) == 1
    assert result[0].close == 70180.20
    # And: client._client remains None (injection did not happen).
    assert client._client is None


@pytest.mark.anyio
async def test_set_http_client_replaces_injected_client() -> None:
    """C2: late-binding setter swaps the underlying client.

    Production uses this to install the lifespan-owned client after
    import time. The setter must overwrite, not merge — a stale
    reference would keep the per-call else-branch on the hot path.
    """
    async with httpx.AsyncClient() as first_client:
        client = BinanceSpotClient(client=first_client)
        assert client._client is first_client

        second_client = httpx.AsyncClient()
        try:
            client.set_http_client(second_client)
            assert client._client is second_client
        finally:
            await second_client.aclose()

        # Setter accepts None to clear (useful for reset between tests).
        client.set_http_client(None)
        assert client._client is None


@pytest.mark.anyio
async def test_fetch_klines_uses_custom_base_url_from_setting() -> None:
    """D2: ``IngestionSettings.binance_base_url`` controls the request URL.

    A custom value is wired through to the client and reflected in
    the request path.
    """
    called_url: str | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called_url
        called_url = str(request.url)
        return httpx.Response(200, json=[])

    settings = IngestionSettings(binance_base_url="https://data-api.binance.vision")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = BinanceSpotClient(
            base_url=settings.binance_base_url,
            client=mock_client,
        )
        await client.fetch_klines(symbol="BTCUSDT", interval="5m", limit=1)

    assert called_url is not None
    assert called_url.startswith("https://data-api.binance.vision/api/v3/klines")


@pytest.mark.anyio
async def test_base_url_strips_trailing_slash() -> None:
    """D2: trailing ``/`` on the base URL is stripped to avoid double-slash."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert "//api/v3" not in str(request.url)
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = BinanceSpotClient(
            base_url="https://api.binance.com/",
            client=mock_client,
        )
        await client.fetch_klines(symbol="BTCUSDT", interval="5m", limit=1)
