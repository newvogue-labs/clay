from pydantic import BaseModel, Field


class ShortlistMetricRow(BaseModel):
    symbol: str
    rolling_volume_score: float
    rolling_volatility_score: float
    liquidity_summary: str
    availability_status: str
    stale_timeframes: list[str] = Field(default_factory=list)
    leader_quote_volume: float = 0.0
    low_quote_volume: bool = False
