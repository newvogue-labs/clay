from datetime import timedelta

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
    binance_base_url: str = "https://api.binance.com"
    binance_retry_after_cap_seconds: float = 60.0
    bybit_spot_enabled: bool = False
    bybit_base_url: str = "https://api.bybit.com"
    market_fetch_max_attempts: int = 2
    market_fetch_retry_delay_seconds: float = 0.5
    news_connector_ids: list[str] = Field(default_factory=lambda: ["demo-news"])
    sentiment_connector_ids: list[str] = Field(
        default_factory=lambda: ["demo-sentiment"],
    )

    # === MP3: config-driven providers — hardcode → settings ===

    market_fetch_limit: int = 200
    market_fetch_timeout: float = 10.0
    market_limits_max_connections: int = 20
    market_limits_max_keepalive: int = 10

    market_freshness_5m_minutes: int = 10
    market_freshness_15m_minutes: int = 25
    market_freshness_1h_minutes: int = 80
    context_freshness_news_hours: int = 8
    context_freshness_sentiment_hours: int = 4

    # === G6-obs: low quote-volume indicator (Finding R3) ===
    # Грубый индикатор ликвидности в USD-обороте: preferred-bar quote_volume
    # (close * volume) ниже порога → low_quote_volume=True в briefing.
    # НЕ используется как gate — только observability-флаг. Env-tunable.
    low_quote_volume_threshold: float = 1_000_000.0

    def market_freshness_thresholds(self) -> dict[str, timedelta]:
        return {
            "5m": timedelta(minutes=self.market_freshness_5m_minutes),
            "15m": timedelta(minutes=self.market_freshness_15m_minutes),
            "1h": timedelta(minutes=self.market_freshness_1h_minutes),
        }

    def context_freshness_thresholds(self) -> dict[str, timedelta]:
        return {
            "news": timedelta(hours=self.context_freshness_news_hours),
            "sentiment": timedelta(hours=self.context_freshness_sentiment_hours),
        }
