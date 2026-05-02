from datetime import UTC, datetime

from clay.db.models_market import MarketBar, MarketFreshnessStatus
from clay.freshness.evaluator import resolve_market_freshness_status
from clay.shortlist.models import ShortlistMetricRow


def build_shortlist_metrics(
    bars: list[MarketBar],
    freshness_rows: list[MarketFreshnessStatus],
) -> list[ShortlistMetricRow]:
    if not bars:
        return []

    max_volume = max(bar.volume for bar in bars) or 1.0
    now = datetime.now(UTC)
    freshness_by_symbol: dict[str, str] = {}
    for row in freshness_rows:
        current = freshness_by_symbol.get(row.symbol, "fresh")
        if current != "fresh":
            continue
        freshness_by_symbol[row.symbol] = resolve_market_freshness_status(
            stored_status=row.freshness_state,
            timeframe=row.timeframe,
            latest_bar_open_time=row.latest_bar_open_time,
            now=now,
        ).status

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

        rows.append(
            ShortlistMetricRow(
                symbol=bar.symbol,
                rolling_volume_score=rolling_volume_score,
                rolling_volatility_score=rolling_volatility_score,
                liquidity_summary=liquidity_summary,
                availability_status=freshness_by_symbol.get(bar.symbol, "unknown"),
            ),
        )

    return rows
