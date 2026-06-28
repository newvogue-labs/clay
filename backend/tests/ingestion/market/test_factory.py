"""Tests for the E3 exchange client factory and config assembly."""

from clay.ingestion.market.binance_client import BinanceSpotClient
from clay.ingestion.market.bybit_client import BybitClient
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
        symbols=[],
        timeframes=[],
    )
    client = build_market_client(cfg)
    assert isinstance(client, BinanceSpotClient)
    assert client.source == "binance_spot"


def test_build_market_client_returns_bybit_client() -> None:
    """E5: factory dispatches to ``BybitClient`` for ``bybit_spot``."""
    cfg = ExchangeConfig(
        exchange_id="bybit_spot",
        source="bybit_spot",
        enabled=True,
        base_url="https://api.bybit.com",
        symbols=[],
        timeframes=[],
    )
    client = build_market_client(cfg)
    assert isinstance(client, BybitClient)
    assert client.source == "bybit_spot"


def test_build_market_client_raises_on_unknown_exchange() -> None:
    """Factory raises ``ValueError`` (fail-fast) for unknown ``exchange_id``."""
    cfg = ExchangeConfig(
        exchange_id="unknown_exchange",
        source="unknown",
        enabled=True,
        base_url="https://example.invalid",
        symbols=[],
        timeframes=[],
    )
    from pytest import raises

    with raises(ValueError, match="unknown exchange_id"):
        build_market_client(cfg)


def test_build_exchanges_map_creates_single_binance_entry() -> None:
    """``bybit_spot_enabled`` defaults to False — only Binance entry."""
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


def test_build_exchanges_map_includes_bybit_when_enabled() -> None:
    """``bybit_spot_enabled=True`` adds second entry with correct insertion order."""
    settings = IngestionSettings(
        binance_spot_enabled=True,
        bybit_spot_enabled=True,
        market_symbols=["BTCUSDT"],
        market_timeframes=["5m"],
        binance_base_url="https://api.binance.com",
        bybit_base_url="https://api-testnet.bybit.com",
    )
    exchanges = build_exchanges_map(settings)
    assert list(exchanges.keys()) == ["binance_spot", "bybit_spot"]
    bybit = exchanges["bybit_spot"]
    assert bybit.source == "bybit_spot"
    assert bybit.base_url == "https://api-testnet.bybit.com"
    assert bybit.symbols == ["BTCUSDT"]
    assert bybit.timeframes == ["5m"]
