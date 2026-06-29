from datetime import UTC, datetime

from clay.db.models_market import MarketBar, MarketFreshnessStatus
from clay.freshness.evaluator import (
    collapse_market_statuses,
    resolve_market_freshness_status,
)
from clay.shortlist.models import ShortlistMetricRow


def build_shortlist_metrics(
    bars: list[MarketBar],
    freshness_rows: list[MarketFreshnessStatus],
    *,
    low_quote_volume_threshold: float = 0.0,
    now: datetime | None = None,
) -> list[ShortlistMetricRow]:
    if not bars:
        return []

    max_volume = max(bar.volume for bar in bars) or 1.0
    now = now if now is not None else datetime.now(UTC)
    evaluated_by_symbol: dict[str, list[str]] = {}
    stale_timeframes_by_symbol: dict[str, list[str]] = {}
    for row in freshness_rows:
        evaluated_status = resolve_market_freshness_status(
            stored_status=row.freshness_state,
            timeframe=row.timeframe,
            latest_bar_open_time=row.latest_bar_open_time,
            now=now,
        ).status
        if evaluated_status != "fresh":
            stale_timeframes_by_symbol.setdefault(row.symbol, []).append(row.timeframe)
        evaluated_by_symbol.setdefault(row.symbol, []).append(evaluated_status)
    freshness_by_symbol = {
        symbol: collapse_market_statuses(statuses)
        for symbol, statuses in evaluated_by_symbol.items()
    }

    rows: list[ShortlistMetricRow] = []
    for bar in bars:
        rolling_volume_score = round(bar.volume / max_volume, 4)
        raw_volatility = abs(bar.high - bar.low) / bar.close if bar.close else 0.0
        rolling_volatility_score = round(min(raw_volatility * 10, 1.0), 4)
        if rolling_volume_score >= 0.75:
            liquidity_summary = "high"
        elif rolling_volume_score >= 0.4:
            liquidity_summary = "medium"
        else:
            liquidity_summary = "low"

        quote_volume = round(bar.close * bar.volume, 4)
        low_quote_volume = (
            low_quote_volume_threshold > 0.0
            and quote_volume < low_quote_volume_threshold
        )

        rows.append(
            ShortlistMetricRow(
                symbol=bar.symbol,
                rolling_volume_score=rolling_volume_score,
                rolling_volatility_score=rolling_volatility_score,
                liquidity_summary=liquidity_summary,
                availability_status=freshness_by_symbol.get(bar.symbol, "unknown"),
                stale_timeframes=sorted(stale_timeframes_by_symbol.get(bar.symbol, [])),
                leader_quote_volume=quote_volume,
                low_quote_volume=low_quote_volume,
            ),
        )

    return rows
