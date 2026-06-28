from datetime import UTC, datetime, timedelta

from clay.freshness.evaluator import (
    evaluate_context_freshness,
    evaluate_market_freshness,
)


def test_market_freshness_becomes_stale_after_threshold() -> None:
    now = datetime(2026, 4, 15, 10, 30, tzinfo=UTC)
    last_bar = now - timedelta(minutes=20)

    result = evaluate_market_freshness(
        timeframe="5m",
        last_received_at=last_bar,
        now=now,
    )

    assert result.status == "stale"
    assert result.blocks_active_trading is True


def test_context_freshness_becomes_degraded_without_blocking_market_only_mode() -> None:
    now = datetime(2026, 4, 15, 10, 30, tzinfo=UTC)
    last_news = now - timedelta(hours=12)

    result = evaluate_context_freshness(
        stream_name="news",
        last_received_at=last_news,
        now=now,
    )

    assert result.status == "degraded"
    assert result.blocks_active_trading is False
