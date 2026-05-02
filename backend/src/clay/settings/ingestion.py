from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestionSettings(BaseSettings):
    """Canonical E2 settings for market/context ingestion and storage."""

    model_config = SettingsConfigDict(
        env_prefix="CLAY_",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://clay:clay@localhost:5432/clay"
    binance_spot_enabled: bool = True
    market_symbols: list[str] = Field(
        default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    )
    market_timeframes: list[str] = Field(
        default_factory=lambda: ["5m", "15m", "1h"],
    )
    market_fetch_max_attempts: int = 2
    market_fetch_retry_delay_seconds: float = 0.5
    news_connector_ids: list[str] = Field(default_factory=lambda: ["demo-news"])
    sentiment_connector_ids: list[str] = Field(
        default_factory=lambda: ["demo-sentiment"],
    )
