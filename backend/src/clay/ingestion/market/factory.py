"""Exchange configuration assembly and client factory for E3 multi-exchange seam."""

from clay.ingestion.market.exchange_config import ExchangeConfig
from clay.ingestion.market.protocol import MarketDataClient
from clay.settings.ingestion import IngestionSettings


def build_market_client(cfg: ExchangeConfig, timeout: float = 10.0) -> MarketDataClient:
    """Create a ``MarketDataClient`` from an ``ExchangeConfig``.

    Raises ``ValueError`` for unknown ``exchange_id`` (fail-fast).
    """
    if cfg.exchange_id == "binance_spot":
        from clay.ingestion.market.binance_client import BinanceSpotClient  # noqa: PLC0415 — lazy import avoids circular deps

        return BinanceSpotClient(
            base_url=cfg.base_url, source=cfg.source, timeout=timeout
        )
    if cfg.exchange_id == "bybit_spot":
        from clay.ingestion.market.bybit_client import BybitClient  # noqa: PLC0415 — lazy import avoids circular deps

        return BybitClient(base_url=cfg.base_url, source=cfg.source, timeout=timeout)
    msg = f"unknown exchange_id: {cfg.exchange_id!r}"
    raise ValueError(msg)


def build_exchanges_map(
    settings: IngestionSettings,
) -> dict[str, ExchangeConfig]:
    """Assemble the exchange-config map from current flat settings.

    At E3 there is exactly one entry (``"binance_spot"``) built from
    the existing ``CLAY_BINANCE_*`` / ``CLAY_MARKET_*`` env vars.
    A future adapter (E4, Bybit) registers a second entry here.

    No new env vars are introduced — backward compat with the flat
    settings is maintained.
    """
    exchanges: dict[str, ExchangeConfig] = {
        "binance_spot": ExchangeConfig(
            exchange_id="binance_spot",
            source="binance_spot",
            enabled=settings.binance_spot_enabled,
            base_url=settings.binance_base_url,
            symbols=list(settings.market_symbols),
            timeframes=list(settings.market_timeframes),
        ),
    }
    if settings.bybit_spot_enabled:
        exchanges["bybit_spot"] = ExchangeConfig(
            exchange_id="bybit_spot",
            source="bybit_spot",
            enabled=True,
            base_url=settings.bybit_base_url,
            symbols=list(settings.market_symbols),
            timeframes=list(settings.market_timeframes),
        )
    return exchanges
