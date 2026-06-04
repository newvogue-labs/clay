"""Tests for the E3 exchange client factory and config assembly."""

from clay.ingestion.market.binance_client import BinanceSpotClient
from clay.ingestion.market.exchange_config import ExchangeConfig
from clay.ingestion.market.factory import build_exchanges_map, build_market_client
from clay.settings.ingestion import IngestionSettings


def test_build_market_client_returns_binance_spot_client() -> None:
    """Factory dispatches to ``BinanceSpotClient`` for ``binance_spot``."""
    cfg = ExchangeConfig(
        exchange_id="binance_spot",
        source="binance_spot",
        enabled=True,
        base_url="https://custom.api.com",
        symbols=[], timeframes=[],
    )
    client = build_market_client(cfg)
    assert isinstance(client, BinanceSpotClient)
    assert client.source == "binance_spot"
    # base_url is stored via _base_url in the client (private, ok for test)
    # Instead: verify source and type.
    del client


def test_build_market_client_raises_on_unknown_exchange() -> None:
    """Factory raises ``ValueError`` (fail-fast) for unknown ``exchange_id``."""
    cfg = ExchangeConfig(
        exchange_id="bybit_spot",
        source="bybit_spot",
        enabled=True,
        base_url="https://api.bybit.com",
        symbols=[], timeframes=[],
    )
    from pytest import raises
    with raises(ValueError, match="unknown exchange_id"):
        build_market_client(cfg)


def test_build_exchanges_map_creates_single_binance_entry() -> None:
    """From flat settings, one entry ``"binance_spot"`` is assembled."""
    settings = IngestionSettings(
        binance_spot_enabled=True,
        market_symbols=["BTCUSDT"],
        market_timeframes=["5m"],
        binance_base_url="https://api.binance.com",
    )
    exchanges = build_exchanges_map(settings)
    assert list(exchanges.keys()) == ["binance_spot"]
    entry = exchanges["binance_spot"]
    assert entry.exchange_id == "binance_spot"
    assert entry.source == "binance_spot"
    assert entry.enabled is True
    assert entry.base_url == "https://api.binance.com"
    assert entry.symbols == ["BTCUSDT"]
    assert entry.timeframes == ["5m"]
