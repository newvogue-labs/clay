from datetime import UTC, datetime, timedelta

from clay.freshness.models import FreshnessResult


MARKET_THRESHOLDS = {
    "5m": timedelta(minutes=10),
    "15m": timedelta(minutes=25),
    "1h": timedelta(minutes=80),
}

CONTEXT_THRESHOLDS = {
    "news": timedelta(hours=8),
    "sentiment": timedelta(hours=4),
}

MARKET_STATUS_PRIORITY = {
    "fresh": 0,
    "unknown": 1,
    "stale": 2,
    "error": 3,
}


def evaluate_market_freshness(
    timeframe: str,
    last_received_at: datetime | None,
    now: datetime,
    *,
    market_thresholds: dict[str, timedelta] | None = None,
) -> FreshnessResult:
    if last_received_at is None:
        return FreshnessResult(
            stream_name=f"market:{timeframe}",
            status="unknown",
            observed_at=now,
            blocks_active_trading=True,
            reason="missing last_received_at",
        )

    last_received_at = _coerce_timezone(last_received_at)
    now = _coerce_timezone(now)
    delta = now - last_received_at
    thresholds = (
        market_thresholds if market_thresholds is not None else MARKET_THRESHOLDS
    )
    threshold = thresholds[timeframe]
    status = "fresh" if delta <= threshold else "stale"
    return FreshnessResult(
        stream_name=f"market:{timeframe}",
        status=status,
        observed_at=now,
        blocks_active_trading=status == "stale",
        reason=f"delta={delta}",
    )


def evaluate_context_freshness(
    stream_name: str,
    last_received_at: datetime | None,
    now: datetime,
    *,
    context_thresholds: dict[str, timedelta] | None = None,
) -> FreshnessResult:
    if last_received_at is None:
        return FreshnessResult(
            stream_name=f"context:{stream_name}",
            status="degraded",
            observed_at=now,
            blocks_active_trading=False,
            reason="missing last_received_at",
        )

    last_received_at = _coerce_timezone(last_received_at)
    now = _coerce_timezone(now)
    thresholds = (
        context_thresholds if context_thresholds is not None else CONTEXT_THRESHOLDS
    )
    delta = now - last_received_at
    threshold = thresholds[stream_name]
    status = "fresh" if delta <= threshold else "degraded"
    return FreshnessResult(
        stream_name=f"context:{stream_name}",
        status=status,
        observed_at=now,
        blocks_active_trading=False,
        reason=f"delta={delta}",
    )


def resolve_market_freshness_status(
    *,
    stored_status: str,
    timeframe: str,
    latest_bar_open_time: datetime | None,
    now: datetime,
    market_thresholds: dict[str, timedelta] | None = None,
) -> FreshnessResult:
    evaluated = evaluate_market_freshness(
        timeframe=timeframe,
        last_received_at=latest_bar_open_time,
        now=now,
        market_thresholds=market_thresholds,
    )
    effective_status = _worse_market_status(stored_status, evaluated.status)
    reason = evaluated.reason
    if effective_status != evaluated.status:
        reason = f"stored_state={stored_status}; {evaluated.reason}"
    return FreshnessResult(
        stream_name=evaluated.stream_name,
        status=effective_status,
        observed_at=evaluated.observed_at,
        blocks_active_trading=effective_status != "fresh",
        reason=reason,
    )


def collapse_market_statuses(statuses: list[str]) -> str:
    if not statuses:
        return "unknown"
    current = "fresh"
    for status in statuses:
        current = _worse_market_status(current, status)
    return current


def _coerce_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _worse_market_status(left: str, right: str) -> str:
    left_priority = MARKET_STATUS_PRIORITY.get(left, MARKET_STATUS_PRIORITY["error"])
    right_priority = MARKET_STATUS_PRIORITY.get(right, MARKET_STATUS_PRIORITY["error"])
    return left if left_priority >= right_priority else right
