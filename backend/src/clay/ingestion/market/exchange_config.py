from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExchangeConfig:
    """Per-exchange configuration for market data ingestion.

    ``exchange_id`` is the logical key (e.g. ``"binance_spot"``).
    ``source`` is the label written to the DB (``source`` column).
    ``symbols`` and ``timeframes`` are per-exchange overrides of the
    global defaults — for Binance they mirror ``market_symbols`` /
    ``market_timeframes``; a future adapter (E4, Bybit) may define
    its own set.
    """

    exchange_id: str
    source: str
    enabled: bool
    base_url: str
    symbols: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=list)
