"""Persistence tests for ``ValidationLabService`` strategy_state (Slice A5).

Slice A5 wires only the ``strategy_state.strategy_mode`` column to
``ValidationLabService._strategy_mode``. The ``target_type='model_assignment'``
activation path is tracked as D2 (separate micro-slice A5.5) — see
``test_apply_activation_model_assignment_does_not_touch_strategy_state``
for the isolation contract that keeps strategy_state clean for now.

Contracts exercised:

- **First-boot:** an empty DB is seeded with a ``strategy_state``
  singleton row (id=1, default ``strategy_mode='momentum'``) on the
  first ``ValidationLabService`` construction with a ``session_factory``.
- **Restart-survival:** an ``apply_activation(target_type='strategy_mode')``
  survives a process restart; the new ``_strategy_mode`` is restored
  from the DB row.
- **D2 isolation:** ``apply_activation(target_type='model_assignment')``
  MUST NOT touch ``strategy_state`` — only ``strategy_mode`` activations
  are wired to the persistence layer in A5.
- **Write-through:** the in-memory ``_strategy_mode`` and the DB row
  are kept consistent via ``StrategyStateRepository.save``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.db.models_ops import StrategyState
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.db.repositories_runtime_state import StrategyStateRepository
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.session_review.service import SessionReviewService
from clay.signal_engine.service import SignalEngineService
from clay.validation_lab.models import ValidationRunCommand
from clay.validation_lab.service import ValidationLabService


def build_service(session_factory: sessionmaker) -> ValidationLabService:
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
    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)
    audit_writer = AuditWriter(config_loader.paths.state_dir)
    event_bus = EventBus()
    ai_control_service = AIControlService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
    )
    signal_engine_service = SignalEngineService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        ai_control_service=ai_control_service,
    )
    session_review_service = SessionReviewService(
        audit_writer=audit_writer,
        event_bus=event_bus,
        ai_control_service=ai_control_service,
    )
    return ValidationLabService(
        signal_engine_service=signal_engine_service,
        ai_control_service=ai_control_service,
        session_review_service=session_review_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
    )


def seed_validation_inputs(session) -> None:
    """Seed minimal market/context data so ``run_validation`` and
    ``review_activation`` succeed with a healthy posture (``ready`` /
    ``staged``, never ``blocked``)."""
    now = datetime.now(UTC)
    market_repository = MarketRepository(session)
    context_repository = ContextRepository(session)
    ops_repository = OpsRepository(session)
    market_repository.upsert_market_bars(
        [
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "open": 70000.0,
                "high": 70600.0,
                "low": 69950.0,
                "close": 70500.0,
                "volume": 250.0,
                "quote_volume": 17600000.0,
                "source": "binance_spot",
                "bar_open_time": now - timedelta(minutes=15),
                "bar_close_time": now - timedelta(minutes=1),
            },
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
    context_repository.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "Replay input is ready",
                "summary": "Context supports a replay run.",
                "published_at": now - timedelta(minutes=30),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/replay",
            },
        ]
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.78,
                "captured_at": now - timedelta(minutes=20),
            },
        ]
    )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    session.commit()


# === First-boot


def test_first_boot_creates_default_strategy_state_row(sqlite_session_factory) -> None:
    build_service(sqlite_session_factory)

    with sqlite_session_factory() as session:
        repo = StrategyStateRepository(session)
        row = repo.read()
        assert row is not None
        assert row.id == 1
        assert row.strategy_mode == "momentum"


def test_first_boot_persists_strategy_state_via_get_or_create(
    sqlite_session_factory,
) -> None:
    build_service(sqlite_session_factory)

    with sqlite_session_factory() as session:
        # Exactly one row exists.
        assert session.scalar(select(func.count()).select_from(StrategyState)) == 1


# === Restart-survival: apply_activation('strategy_mode')


def test_restart_survives_apply_activation_strategy_mode(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    seed_validation_inputs(db_session)
    service1.run_validation(
        db_session,
        ValidationRunCommand(run_type="strategy_replay", label="Momentum replay"),
    )
    review = service1.review_activation(
        db_session,
        target_type="strategy_mode",
        target_id="global-strategy",
        proposed_value="defensive",
    )
    service1.apply_activation(db_session, review.review_id)

    # apply_activation does session.commit() internally; verify the row.
    with sqlite_session_factory() as session:
        row = StrategyStateRepository(session).read()
        assert row is not None
        assert row.strategy_mode == "defensive"

    # Brand-new service instance → simulates a process restart.
    service2 = build_service(sqlite_session_factory)
    assert service2._strategy_mode == "defensive"


# === D2 isolation: model_assignment must NOT touch strategy_state


def test_apply_activation_model_assignment_does_not_touch_strategy_state(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    """D2 (tracked for A5.5): ``apply_activation(target_type='model_assignment')``
    mutates ``ai_control_service.assignments`` directly, bypassing both
    ``ai_control_service.apply_assignment`` (A3 write-through) and
    ``strategy_state`` (this slice). For now, the slice MUST keep
    ``strategy_state`` clean: a model-assignment activation must not
    change ``_strategy_mode`` and must not write a ``strategy_state``
    row.
    """
    service1 = build_service(sqlite_session_factory)
    seed_validation_inputs(db_session)
    service1.run_validation(
        db_session,
        ValidationRunCommand(run_type="model_comparison", label="Model compare"),
    )
    review = service1.review_activation(
        db_session,
        target_type="model_assignment",
        target_id="forecast-model",
        proposed_value="forecast-lite-v1",
    )

    assert service1._strategy_mode == "momentum"  # unchanged before apply
    service1.apply_activation(db_session, review.review_id)
    assert service1._strategy_mode == "momentum"  # STILL unchanged after apply

    # DB-level: strategy_state row still says momentum.
    with sqlite_session_factory() as session:
        row = StrategyStateRepository(session).read()
        assert row is not None
        assert row.strategy_mode == "momentum"

    # After restart, ``_strategy_mode`` is restored to ``momentum`` (the
    # default at first boot), confirming the model_assignment path did
    # not persist anything to strategy_state.
    service2 = build_service(sqlite_session_factory)
    assert service2._strategy_mode == "momentum"


# === Slice A5.5: apply_activation('model_assignment') persists via ai_control


def test_apply_activation_model_assignment_persists_via_ai_control(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    """A5.5 (D2 fix): ``apply_activation(target_type='model_assignment')``
    now routes through ``ai_control.set_assignment`` (the trusted
    internal-caller path), so the new mapping is written to
    ``ai_assignments`` and survives a process restart — closing the D2
    durability hole that the A5-isolation test temporarily documented.

    Restart-survival is the headline acceptance criterion: a brand-new
    ``ValidationLabService`` + ``AIControlService`` pair on the same DB
    must see the promoted model_id.
    """
    from clay.db.repositories_runtime_state import AIAssignmentRepository

    service1 = build_service(sqlite_session_factory)
    seed_validation_inputs(db_session)
    service1.run_validation(
        db_session,
        ValidationRunCommand(
            run_type="model_comparison", label="Promote forecast-lite"
        ),
    )
    review = service1.review_activation(
        db_session,
        target_type="model_assignment",
        target_id="forecast-model",
        proposed_value="forecast-lite-v1",
    )
    service1.apply_activation(db_session, review.review_id)

    # In-memory state in BOTH services reflects the promotion.
    assert (
        service1.ai_control_service.assignments["forecast-model"] == "forecast-lite-v1"
    )

    # DB-level: the row was actually written to ai_assignments (not just
    # mutated in-memory as the pre-A5.5 direct-dict path did).
    with sqlite_session_factory() as session:
        repo = AIAssignmentRepository(session)
        assert repo.read_all()["forecast-model"] == "forecast-lite-v1"
        # Other roles kept their initial mapping.
        assert repo.read_all()["chief-agent"] == "minimax-m3"

    # Brand-new service instance → simulates a process restart against
    # the same DB. The promoted assignment MUST survive.
    service2 = build_service(sqlite_session_factory)
    assert (
        service2.ai_control_service.assignments["forecast-model"] == "forecast-lite-v1"
    )
    assert service2.ai_control_service.assignments["chief-agent"] == "minimax-m3"


# === typing sanity


def test_typing_strategy_state_columns() -> None:
    from clay.db.models_ops import StrategyState as Model

    expected = {"id", "strategy_mode", "updated_at"}
    assert expected.issubset(set(Model.__annotations__.keys()))
    assert cast(type, Model) is StrategyState
