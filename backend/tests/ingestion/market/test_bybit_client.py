"""Tests for ``BybitClient`` — E4 isolated adapter.

0 wiring, 0 live flow — all tests use ``httpx.MockTransport``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from clay.ingestion.market.bybit_client import BybitApiError, BybitClient
from clay.ingestion.market.models import NormalizedMarketBar

_BAR_RAW: list[str] = [
    "1711954800000",
    "70250.10",
    "70420.00",
    "70180.40",
    "70390.20",
    "123.45",
    "8670000.10",
]

_BYBIT_OK = {"retCode": 0, "retMsg": "OK", "result": {"list": [_BAR_RAW]}}


@pytest.mark.anyio
async def test_fetch_klines_returns_normalized_bars() -> None:
    """Happy path: raw Bybit kline → ``NormalizedMarketBar``."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/market/kline"
        return httpx.Response(200, json=_BYBIT_OK)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as mock_client:
        client = BybitClient(base_url="https://test.invalid", client=mock_client)
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
    assert bar.source == "bybit_spot"
    assert bar.bar_open_time == datetime(2024, 4, 1, 7, 0, tzinfo=UTC)
    assert bar.bar_close_time == datetime(2024, 4, 1, 7, 4, 59, 999000, tzinfo=UTC)


@pytest.mark.anyio
async def test_reverses_newest_first_to_ascending() -> None:
    """Bybit returns newest-first; client reverses to oldest-first."""
    bars = [
        ["1711956600000", "70300", "70400", "70200", "70350", "50", "3517500"],
        ["1711954800000", "70250", "70420", "70180", "70390", "123", "8670000"],
        ["1711953000000", "70100", "70200", "70050", "70180", "200", "14000000"],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"retCode": 0, "retMsg": "OK", "result": {"list": bars}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = BybitClient(base_url="https://test.invalid", client=mock_client)
        result = await client.fetch_klines(symbol="BTCUSDT", interval="5m", limit=3)

    assert len(result) == 3
    open_times = [b.bar_open_time for b in result]
    assert open_times == sorted(open_times)


@pytest.mark.anyio
async def test_close_time_pin_five_minute() -> None:
    """5m bar open=T → close == T+300_000−1 ms — matches Binance convention."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_BYBIT_OK)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = BybitClient(base_url="https://test.invalid", client=mock_client)
        result = await client.fetch_klines(symbol="BTCUSDT", interval="5m", limit=1)

    bar = result[0]
    expected_close = datetime(2024, 4, 1, 7, 4, 59, 999000, tzinfo=UTC)
    assert bar.bar_close_time == expected_close


@pytest.mark.anyio
async def test_close_time_pin_one_hour() -> None:
    """1h bar: duration 3_600_000 ms."""
    raw = ["1711954800000", "70250", "70420", "70180", "70390", "123", "8670000"]
    ok = {"retCode": 0, "retMsg": "OK", "result": {"list": [raw]}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ok)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = BybitClient(base_url="https://test.invalid", client=mock_client)
        result = await client.fetch_klines(symbol="BTCUSDT", interval="1h", limit=1)

    bar = result[0]
    expected_close = datetime(2024, 4, 1, 7, 59, 59, 999000, tzinfo=UTC)
    assert bar.bar_close_time == expected_close


@pytest.mark.anyio
async def test_one_month_interval_raises_on_fetch() -> None:
    """1M has variable duration — fetch must raise ValueError, not silently miscompute."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_BYBIT_OK)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = BybitClient(base_url="https://test.invalid", client=mock_client)
        with pytest.raises(ValueError, match="variable duration"):
            await client.fetch_klines(symbol="BTCUSDT", interval="1M", limit=1)


@pytest.mark.anyio
async def test_bybit_error_ret_code_nonzero_raises() -> None:
    """HTTP 200 but retCode != 0 → ``BybitApiError``."""
    error_response = {
        "retCode": 10001,
        "retMsg": "invalid symbol",
        "result": {},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=error_response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = BybitClient(base_url="https://test.invalid", client=mock_client)
        with pytest.raises(BybitApiError) as exc_info:
            await client.fetch_klines(symbol="INVALID", interval="5m", limit=1)

    assert exc_info.value.ret_code == 10001
    assert "invalid symbol" in str(exc_info.value)


@pytest.mark.anyio
async def test_unknown_interval_raises_value_error() -> None:
    """Unsupported interval → ValueError (fail-fast)."""
    client = BybitClient()
    with pytest.raises(ValueError, match="unknown interval"):
        await client.fetch_klines(symbol="BTCUSDT", interval="13m", limit=1)


def test_source_default() -> None:
    """Default source is ``bybit_spot``."""
    client = BybitClient()
    assert client.source == "bybit_spot"


def test_source_overridable() -> None:
    """Source is overridable via constructor."""
    client = BybitClient(source="test_bybit")
    assert client.source == "test_bybit"


@pytest.mark.anyio
async def test_base_url_strips_trailing_slash() -> None:
    """Trailing ``/`` stripped to avoid double-slash in request."""
    seen_url: str | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_url
        seen_url = str(request.url)
        return httpx.Response(200, json=_BYBIT_OK)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = BybitClient(base_url="https://api.bybit.com/", client=mock_client)
        await client.fetch_klines(symbol="BTCUSDT", interval="5m", limit=1)

    assert seen_url is not None
    assert "//v5/" not in seen_url  # no double slash
    assert seen_url.startswith("https://api.bybit.com/v5/market/kline")


@pytest.mark.anyio
async def test_set_http_client_replaces_injected_client() -> None:
    """Late-binding setter swaps the underlying client (mirror BinanceSpotClient)."""
    async with httpx.AsyncClient() as first_client:
        client = BybitClient(client=first_client)
        assert client._client is first_client

        second_client = httpx.AsyncClient()
        try:
            client.set_http_client(second_client)
            assert client._client is second_client
        finally:
            await second_client.aclose()

        client.set_http_client(None)
        assert client._client is None


@pytest.mark.anyio
async def test_per_call_fallback_produces_identical_result() -> None:
    """No injected client → per-call AsyncClient path; result matches injected path."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/market/kline"
        assert request.url.params["category"] == "spot"
        return httpx.Response(200, json=_BYBIT_OK)

    import clay.ingestion.market.bybit_client as bybit_module

    original_async_client = bybit_module.httpx.AsyncClient

    class _PatchedAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            self._client = original_async_client(
                transport=httpx.MockTransport(handler),
                *args,
                **kwargs,
            )

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, *args):
            return await self._client.__aexit__(*args)

    bybit_module.httpx.AsyncClient = _PatchedAsyncClient
    try:
        client = BybitClient(base_url="https://test.invalid")
        result = await client.fetch_klines(symbol="BTCUSDT", interval="5m", limit=1)
    finally:
        bybit_module.httpx.AsyncClient = original_async_client

    assert len(result) == 1
    assert result[0].close == 70390.20
    assert client._client is None


@pytest.mark.anyio
async def test_interval_map_all_supported() -> None:
    """All intervals in ``_INTERVAL_MAP`` produce a valid Bybit interval string."""
    cases = [
        ("1m", "1"),
        ("3m", "3"),
        ("5m", "5"),
        ("15m", "15"),
        ("30m", "30"),
        ("1h", "60"),
        ("2h", "120"),
        ("4h", "240"),
        ("6h", "360"),
        ("12h", "720"),
        ("1d", "D"),
        ("1w", "W"),
        ("1M", "M"),
    ]
    for canonical, expected in cases:
        assert BybitClient._map_interval(canonical) == expected


@pytest.mark.anyio
async def test_empty_list_response() -> None:
    """Bybit may return an empty list — client returns empty list."""
    ok_empty = {"retCode": 0, "retMsg": "OK", "result": {"list": []}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ok_empty)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = BybitClient(base_url="https://test.invalid", client=mock_client)
        result = await client.fetch_klines(symbol="BTCUSDT", interval="5m", limit=1)

    assert result == []
