"""Unit tests for ``_resolve_retry_delay``.

D3: the helper is a module-level pure function in
``clay.ingestion.service``.  All tests use synthetic
``httpx.HTTPStatusError`` exceptions with mocked ``response``
objects.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email import utils as email_utils

import httpx

from clay.ingestion.service import _resolve_retry_delay


def _make_rate_limit_error(
    status_code: int = 429,
    retry_after: str | None = None,
) -> httpx.HTTPStatusError:
    """Build a synthetic HTTPStatusError with optional Retry-After header."""
    headers: dict[str, str] = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    request = httpx.Request("GET", "https://api.binance.com/api/v3/klines")
    response = httpx.Response(status_code, headers=headers, request=request)
    return httpx.HTTPStatusError(
        "rate limited",
        request=request,
        response=response,
    )


def _make_generic_error(status_code: int = 500) -> httpx.HTTPStatusError:
    """Build a synthetic non-rate-limit HTTP error."""
    request = httpx.Request("GET", "https://api.binance.com/api/v3/klines")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        "server error",
        request=request,
        response=response,
    )


class TestResolveRetryDelaySeconds:
    """Retry-After in seconds format."""

    def test_seconds_format(self) -> None:
        assert (
            _resolve_retry_delay(
                _make_rate_limit_error(retry_after="5"),
                default_delay=0.5,
                cap=60.0,
            )
            == 5.0
        )

    def test_value_exceeds_cap(self) -> None:
        assert (
            _resolve_retry_delay(
                _make_rate_limit_error(retry_after="300"),
                default_delay=0.5,
                cap=60.0,
            )
            == 60.0
        )

    def test_negative_value_returns_zero(self) -> None:
        assert (
            _resolve_retry_delay(
                _make_rate_limit_error(retry_after="-10"),
                default_delay=0.5,
                cap=60.0,
            )
            == 0.0
        )

    def test_zero_seconds(self) -> None:
        assert (
            _resolve_retry_delay(
                _make_rate_limit_error(retry_after="0"),
                default_delay=0.5,
                cap=60.0,
            )
            == 0.0
        )


class TestResolveRetryDelayHttpDate:
    """Retry-After in HTTP-date format (RFC 7231)."""

    def test_future_date_returns_positive_delta(self) -> None:
        future = datetime.now(UTC) + timedelta(seconds=30)
        date_str = email_utils.format_datetime(future)
        delay = _resolve_retry_delay(
            _make_rate_limit_error(retry_after=date_str),
            default_delay=0.5,
            cap=120.0,
        )
        assert 25.0 <= delay <= 35.0

    def test_past_date_returns_zero(self) -> None:
        past = datetime.now(UTC) - timedelta(seconds=60)
        date_str = email_utils.format_datetime(past)
        assert (
            _resolve_retry_delay(
                _make_rate_limit_error(retry_after=date_str),
                default_delay=0.5,
                cap=60.0,
            )
            == 0.0
        )

    def test_date_exceeds_cap(self) -> None:
        far_future = datetime.now(UTC) + timedelta(seconds=300)
        date_str = email_utils.format_datetime(far_future)
        assert (
            _resolve_retry_delay(
                _make_rate_limit_error(retry_after=date_str),
                default_delay=0.5,
                cap=60.0,
            )
            == 60.0
        )


class TestResolveRetryDelayFallback:
    """Cases that fall back to ``default_delay``."""

    def test_no_retry_after_header(self) -> None:
        assert (
            _resolve_retry_delay(
                _make_rate_limit_error(retry_after=None),
                default_delay=0.5,
                cap=60.0,
            )
            == 0.5
        )

    def test_garbage_value(self) -> None:
        assert (
            _resolve_retry_delay(
                _make_rate_limit_error(retry_after="abc"),
                default_delay=0.5,
                cap=60.0,
            )
            == 0.5
        )

    def test_non_rate_limit_status(self) -> None:
        assert (
            _resolve_retry_delay(
                _make_generic_error(status_code=500),
                default_delay=0.5,
                cap=60.0,
            )
            == 0.5
        )

    def test_non_http_exception(self) -> None:
        assert (
            _resolve_retry_delay(
                ValueError("not http"),
                default_delay=0.5,
                cap=60.0,
            )
            == 0.5
        )

    def test_418_also_honoured(self) -> None:
        """418 (IP-ban) is treated the same as 429."""
        assert (
            _resolve_retry_delay(
                _make_rate_limit_error(status_code=418, retry_after="10"),
                default_delay=0.5,
                cap=60.0,
            )
            == 10.0
        )
