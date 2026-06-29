from datetime import UTC, datetime, timedelta

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.settings.ingestion import IngestionSettings
from clay.signal_engine.service import SignalEngineService
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from tests.support.factories import make_ingestion_settings


def build_signal_engine(
    ingestion_settings: IngestionSettings | None = None,
) -> SignalEngineService:
    registry = ServiceRegistry()
    registry.register(
        service_id="control-api",
        service_type="api",
        criticality=ServiceCriticality.CRITICAL,
        startup_policy="always-on",
    )
    registry.update_status("control-api", ServiceStatus.HEALTHY)
    config_loader = ConfigLoader()
    config_loader.ensure_default_configs()
    config_loader.load_all()
    ai_control_service = AIControlService(
        runtime_manager=RuntimeManager(registry=registry),
        preflight_service=PreflightService(registry),
        config_loader=config_loader,
        audit_writer=AuditWriter(config_loader.paths.state_dir),
        event_bus=EventBus(),
    )
    return SignalEngineService(
        runtime_manager=RuntimeManager(registry=registry),
        preflight_service=PreflightService(registry),
        config_loader=config_loader,
        ai_control_service=ai_control_service,
        ingestion_settings=ingestion_settings,
    )


def seed_signal_data(session) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(session)
    context_repository = ContextRepository(session)
    ops_repository = OpsRepository(session)
    for symbol, close, volume in [
        ("BTCUSDT", 70540.0, 260.0),
        ("SOLUSDT", 179.1, 95.0),
    ]:
        market_repository.upsert_market_bars(
            [
                {
                    "symbol": symbol,
                    "timeframe": "15m",
                    "open": close * 0.99,
                    "high": close * 1.01,
                    "low": close * 0.985,
                    "close": close,
                    "volume": volume,
                    "quote_volume": close * volume,
                    "source": "binance_spot",
                    "bar_open_time": now - timedelta(minutes=15),
                    "bar_close_time": now - timedelta(minutes=1),
                }
            ]
        )
        market_repository.upsert_freshness_status(
            symbol=symbol,
            timeframe="15m",
            source="binance_spot",
            freshness_state="fresh",
            evaluated_at=now,
            latest_bar_open_time=now - timedelta(minutes=15),
            is_stale=False,
        )
    context_repository.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "BTC keeps leadership",
                "summary": "Momentum stays constructive.",
                "published_at": now - timedelta(minutes=25),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/btc",
            }
        ]
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.81,
                "captured_at": now - timedelta(minutes=10),
            }
        ]
    )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    session.commit()


def test_signal_engine_applies_context_penalties_and_risk_actions(db_session) -> None:
    engine = build_signal_engine()
    seed_signal_data(db_session)

    snapshot = engine.build_snapshot(db_session)

    assert snapshot.signals
    btc = next(signal for signal in snapshot.signals if signal.symbol == "BTCUSDT")
    sol = next(signal for signal in snapshot.signals if signal.symbol == "SOLUSDT")
    assert btc.ranking_score >= sol.ranking_score
    assert sol.response_action in {"lower_confidence", "block_signal", "warning_only"}
    assert any(trigger.title == "Low context quality" for trigger in sol.risk_triggers)


def test_signal_engine_switches_to_defensive_when_runtime_is_degraded(
    db_session,
) -> None:
    engine = build_signal_engine()
    seed_signal_data(db_session)
    engine.runtime_manager.enter_degraded()

    snapshot = engine.build_snapshot(db_session)

    assert snapshot.workspace_posture == "restricted_by_degraded"
    assert snapshot.strategy_mode_proposal == "defensive"
    assert any(
        signal.response_action == "switch_to_defensive" for signal in snapshot.signals
    )


# === G6-obs: observability fields (Finding M, L, R3) ===
# Эти тесты проверяют, что новые read-only диагностические поля
# присутствуют и заполняются корректно. 0 изменений в gate/can_start/порогах.


def test_signal_engine_emits_applied_penalties_for_provider_mix(db_session) -> None:
    engine = build_signal_engine()
    seed_signal_data(db_session)

    snapshot = engine.build_snapshot(db_session)

    btc = next(signal for signal in snapshot.signals if signal.symbol == "BTCUSDT")
    sol = next(signal for signal in snapshot.signals if signal.symbol == "SOLUSDT")

    # Finding M: ai-conflict от hardcoded INITIAL_ASSIGNMENTS → applied_penalties
    # содержит структурированную запись с trigger/delta/note.
    assert btc.applied_penalties, "BTCUSDT должен иметь applied_penalties (ai-conflict)"
    ai_conflict = next(
        (p for p in btc.applied_penalties if p.trigger == "ai-conflict"),
        None,
    )
    assert ai_conflict is not None
    assert ai_conflict.delta == -0.08
    assert "provider-mix" in ai_conflict.note
    assert "chief=" in ai_conflict.note
    # Конфликтующие провайдеры (на live INITIAL_ASSIGNMENTS — Anthropic + Google).
    assert "news-sentiment-agent=" in ai_conflict.note
    assert "forecast-model=" in ai_conflict.note

    # SOLUSDT: thin-context + ai-conflict → минимум 2 penalty.
    sol_triggers = {p.trigger for p in sol.applied_penalties}
    assert "ai-conflict" in sol_triggers
    assert any(t.startswith("thin-context") for t in sol_triggers)


def test_signal_engine_reports_stale_timeframes(db_session) -> None:
    engine = build_signal_engine()
    now = datetime.now(UTC)
    market_repository = MarketRepository(db_session)
    context_repository = ContextRepository(db_session)
    ops_repository = OpsRepository(db_session)

    # Seed BTCUSDT 3 timeframes: 5m + 15m fresh, 1h stale (latest_bar_open_time = now-3h).
    for timeframe, age_minutes in [("5m", 3), ("15m", 10), ("1h", 180)]:
        market_repository.upsert_market_bars(
            [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": timeframe,
                    "open": 70500.0,
                    "high": 70600.0,
                    "low": 70400.0,
                    "close": 70540.0,
                    "volume": 260.0,
                    "quote_volume": 18360400.0,
                    "source": "binance_spot",
                    "bar_open_time": now - timedelta(minutes=age_minutes + 15),
                    "bar_close_time": now - timedelta(minutes=age_minutes),
                }
            ]
        )
        market_repository.upsert_freshness_status(
            symbol="BTCUSDT",
            timeframe=timeframe,
            source="binance_spot",
            freshness_state="fresh",
            evaluated_at=now,
            latest_bar_open_time=now - timedelta(minutes=age_minutes),
            is_stale=False,
        )
    context_repository.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "BTC keeps leadership",
                "summary": "Momentum stays constructive.",
                "published_at": now - timedelta(minutes=25),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/btc",
            }
        ]
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.81,
                "captured_at": now - timedelta(minutes=10),
            }
        ]
    )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    db_session.commit()

    snapshot = engine.build_snapshot(db_session)

    btc = next(signal for signal in snapshot.signals if signal.symbol == "BTCUSDT")

    # Finding L: stale_timeframes содержит ТОЛЬКО "1h" (5m/15m fresh).
    assert btc.stale_timeframes == ["1h"]

    # Гардрейл: ranking/response_action вычислены (т.е. snapshot собран без падений);
    # саму политику first-row-wins этот тест не валидирует — это by-design (G6-R R1).
    assert btc.ranking_score >= 0.0
    assert btc.state in {"active", "weakening", "absent", "invalidated"}


def test_signal_engine_flags_low_quote_volume(db_session) -> None:
    engine = build_signal_engine()
    now = datetime.now(UTC)
    market_repository = MarketRepository(db_session)
    context_repository = ContextRepository(db_session)
    ops_repository = OpsRepository(db_session)

    # BTCUSDT: low quote-volume. close=70540, volume=10 → quote_volume=705,400 (< 1M).
    # SOLUSDT: high quote-volume. close=179, volume=100000 → quote_volume=17,900,000 (> 1M).
    for symbol, close, volume in [
        ("BTCUSDT", 70540.0, 10.0),
        ("SOLUSDT", 179.0, 100_000.0),
    ]:
        market_repository.upsert_market_bars(
            [
                {
                    "symbol": symbol,
                    "timeframe": "15m",
                    "open": close * 0.99,
                    "high": close * 1.01,
                    "low": close * 0.985,
                    "close": close,
                    "volume": volume,
                    "quote_volume": close * volume,
                    "source": "binance_spot",
                    "bar_open_time": now - timedelta(minutes=15),
                    "bar_close_time": now - timedelta(minutes=1),
                }
            ]
        )
        market_repository.upsert_freshness_status(
            symbol=symbol,
            timeframe="15m",
            source="binance_spot",
            freshness_state="fresh",
            evaluated_at=now,
            latest_bar_open_time=now - timedelta(minutes=15),
            is_stale=False,
        )
    context_repository.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "BTC keeps leadership",
                "summary": "Momentum stays constructive.",
                "published_at": now - timedelta(minutes=25),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/btc",
            }
        ]
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.81,
                "captured_at": now - timedelta(minutes=10),
            }
        ]
    )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    db_session.commit()

    snapshot = engine.build_snapshot(db_session)

    btc = next(signal for signal in snapshot.signals if signal.symbol == "BTCUSDT")
    sol = next(signal for signal in snapshot.signals if signal.symbol == "SOLUSDT")

    # R3: BTCUSDT thin → low_quote_volume=True, leader_quote_volume=705,400.
    assert round(btc.leader_quote_volume, 2) == 705_400.0
    assert btc.low_quote_volume is True

    # SOLUSDT liquid → low_quote_volume=False, leader_quote_volume=17,900,000.
    assert round(sol.leader_quote_volume, 2) == 17_900_000.0
    assert sol.low_quote_volume is False

    # Гардрейл: liquidity_summary (rank-based) остаётся в своей семантике —
    # этот тест НЕ ассертит liquidity_summary напрямую, т.к. она не наша цель.


def test_signal_engine_volume_floor_disabled_by_default(db_session) -> None:
    # R3: дефолт min_quote_volume_floor=0.0 → guard ВЫКЛЮЧЕН. Тонкий объём
    # поднимает advisory-флаг (1M), но сигнал НЕ блокируется (dual-tier).
    engine = build_signal_engine()
    now = datetime.now(UTC)
    market_repository = MarketRepository(db_session)
    # BTCUSDT thin: close=70540, volume=10 → quote_volume=705_400 (< 1M advisory).
    market_repository.upsert_market_bars(
        [
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "open": 70540.0 * 0.99,
                "high": 70540.0 * 1.01,
                "low": 70540.0 * 0.985,
                "close": 70540.0,
                "volume": 10.0,
                "quote_volume": 70540.0 * 10.0,
                "source": "binance_spot",
                "bar_open_time": now - timedelta(minutes=15),
                "bar_close_time": now - timedelta(minutes=1),
            }
        ]
    )
    market_repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        source="binance_spot",
        freshness_state="fresh",
        evaluated_at=now,
        latest_bar_open_time=now - timedelta(minutes=15),
        is_stale=False,
    )
    db_session.commit()

    snapshot = engine.build_snapshot(db_session)
    btc = next(s for s in snapshot.signals if s.symbol == "BTCUSDT")

    # advisory работает...
    assert btc.low_quote_volume is True
    # ...но guard выключен: ни триггера, ни блока.
    assert not any(
        t.trigger_id.startswith("low-volume-floor") for t in btc.risk_triggers
    )


def test_signal_engine_blocks_signal_below_volume_floor(db_session) -> None:
    # R3: floor=1_000_000 включён. BTC (705_400) ниже пола → block_signal/invalidated;
    # SOL (17_900_000) выше пола → guard не задет.
    engine = build_signal_engine(
        ingestion_settings=make_ingestion_settings(min_quote_volume_floor=1_000_000.0)
    )
    now = datetime.now(UTC)
    market_repository = MarketRepository(db_session)
    for symbol, close, volume in [
        ("BTCUSDT", 70540.0, 10.0),
        ("SOLUSDT", 179.0, 100_000.0),
    ]:
        market_repository.upsert_market_bars(
            [
                {
                    "symbol": symbol,
                    "timeframe": "15m",
                    "open": close * 0.99,
                    "high": close * 1.01,
                    "low": close * 0.985,
                    "close": close,
                    "volume": volume,
                    "quote_volume": close * volume,
                    "source": "binance_spot",
                    "bar_open_time": now - timedelta(minutes=15),
                    "bar_close_time": now - timedelta(minutes=1),
                }
            ]
        )
        market_repository.upsert_freshness_status(
            symbol=symbol,
            timeframe="15m",
            source="binance_spot",
            freshness_state="fresh",
            evaluated_at=now,
            latest_bar_open_time=now - timedelta(minutes=15),
            is_stale=False,
        )
    db_session.commit()

    snapshot = engine.build_snapshot(db_session)
    btc = next(s for s in snapshot.signals if s.symbol == "BTCUSDT")
    sol = next(s for s in snapshot.signals if s.symbol == "SOLUSDT")

    # BTC ниже пола → guard-триггер + block_signal + invalidated.
    assert any(t.trigger_id == "low-volume-floor-btcusdt" for t in btc.risk_triggers)
    assert btc.response_action == "block_signal"
    assert btc.state == "invalidated"

    # SOL выше пола → guard не сработал.
    assert not any(
        t.trigger_id.startswith("low-volume-floor") for t in sol.risk_triggers
    )
