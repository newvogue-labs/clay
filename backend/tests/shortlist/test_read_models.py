from datetime import UTC, datetime

from clay.db.models_market import MarketBar, MarketFreshnessStatus
from clay.shortlist.read_models import build_shortlist_metrics


def _bar(symbol: str, now: datetime) -> MarketBar:
    return MarketBar(
        source="binance",
        symbol=symbol,
        timeframe="15m",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1000.0,
        bar_open_time=now,
        bar_close_time=now,
    )


def _freshness(
    symbol: str,
    timeframe: str,
    state: str,
    now: datetime,
) -> MarketFreshnessStatus:
    return MarketFreshnessStatus(
        source="binance",
        symbol=symbol,
        timeframe=timeframe,
        freshness_state=state,
        is_stale=state != "fresh",
        evaluated_at=now,
        latest_bar_open_time=now,
    )


def test_availability_status_is_worst_of_across_timeframes() -> None:
    now = datetime(2026, 4, 15, 10, 30, tzinfo=UTC)
    bars = [_bar("SOLUSDT", now)]
    freshness_rows = [
        _freshness("SOLUSDT", "5m", "stale", now),
        _freshness("SOLUSDT", "15m", "error", now),
    ]

    metrics = build_shortlist_metrics(bars, freshness_rows, now=now)

    assert metrics[0].availability_status == "error"
    assert metrics[0].stale_timeframes == ["15m", "5m"]


def test_availability_status_worst_of_is_order_independent() -> None:
    now = datetime(2026, 4, 15, 10, 30, tzinfo=UTC)
    bars = [_bar("SOLUSDT", now)]

    forward = build_shortlist_metrics(
        bars,
        [
            _freshness("SOLUSDT", "5m", "stale", now),
            _freshness("SOLUSDT", "15m", "error", now),
        ],
        now=now,
    )
    reverse = build_shortlist_metrics(
        bars,
        [
            _freshness("SOLUSDT", "15m", "error", now),
            _freshness("SOLUSDT", "5m", "stale", now),
        ],
        now=now,
    )

    assert forward[0].availability_status == "error"
    assert reverse[0].availability_status == "error"
