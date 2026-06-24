"""Persistence tests for ``SessionControlService``.

These tests exercise the Slice A4 contract:

- **First-boot:** an empty DB is seeded with a ``session_state`` singleton
  row (id=1, all 10 fields ``None``) on the first
  ``SessionControlService`` construction with a ``session_factory``.
- **Restart-survival:** a ``SessionControlService`` constructed against a
  DB that has prior writes (start / pause / resume / replace) restores
  the persisted ``_active_session`` and ``_pending_replacement`` instead
  of using defaults.
- **Write-through:** all 6 mutators (``start`` / ``pause`` / ``resume`` /
  ``complete`` / ``review_pair_replacement`` / ``apply_pair_replacement``)
  persist their changes through the supplied ``Session``; the service's
  in-memory state stays consistent with what is on disk.
- **Discriminator-based restore:** ``session_id is None`` → no active
  session. ``session_id is not None`` → all other required fields must
  be populated, otherwise ``ValueError`` (fail-fast on inconsistent row).
- **TZ-aware round-trips** (Slice A2.5): ``paused_at`` keeps ``tzinfo``
  through SQLite.

The repository layer is bypassed for some direct DB asserts (``select``
+ ``func.count()``) to keep the test honest about what was actually
written, not just what the service claims it wrote.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.db.models_ops import SessionState
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.db.repositories_runtime_state import SessionStateRepository
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.session_control.service import SessionControlService
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService


def build_service(session_factory: sessionmaker) -> SessionControlService:
    registry = ServiceRegistry()
    registry.register(
        service_id="control-api",
        service_type="api",
        criticality=ServiceCriticality.CRITICAL,
        startup_policy="always-on",
    )
    registry.update_status("control-api", ServiceStatus.HEALTHY)

    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)
    config_loader = ConfigLoader()
    config_loader.ensure_default_configs()
    config_loader.load_all()
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
    workspace_service = WorkspaceService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        registry=registry,
        signal_engine_service=signal_engine_service,
    )
    return SessionControlService(
        runtime_manager=runtime_manager,
        signal_engine_service=signal_engine_service,
        ai_control_service=ai_control_service,
        workspace_service=workspace_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
        config_loader=ConfigLoader(),
    )


def seed_session_data(session) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(session)
    context_repository = ContextRepository(session)
    ops_repository = OpsRepository(session)

    for symbol, close, volume in [("BTCUSDT", 70540.0, 260.0), ("SOLUSDT", 181.5, 320.0)]:
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
                },
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
                "headline": "BTC and SOL remain constructive",
                "summary": "Intraday structure still supports a session start.",
                "published_at": now - timedelta(minutes=20),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/session",
            },
            {
                "source_name": "demo_news_feed",
                "headline": "SOL gains momentum",
                "summary": "Rotation toward SOL improves relative ranking.",
                "published_at": now - timedelta(minutes=10),
                "symbol": "SOLUSDT",
                "source_url": "https://example.invalid/news/sol",
            },
        ]
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.74,
                "captured_at": now - timedelta(minutes=12),
            },
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "SOLUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.88,
                "captured_at": now - timedelta(minutes=8),
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


# === First-boot seeding


def test_first_boot_creates_empty_session_state_row(sqlite_session_factory) -> None:
    build_service(sqlite_session_factory)

    with sqlite_session_factory() as session:
        repo = SessionStateRepository(session)
        row = repo.read()
        assert row is not None
        assert row.id == 1
        # Discriminator fields: no active session, no pending replacement.
        assert row.session_id is None
        assert row.pending_replacement_id is None
        # The other 8 fields are nullable and must default to None.
        assert row.current_pair_symbol is None
        assert row.current_signal_id is None
        assert row.strategy_mode is None
        assert row.started_at is None
        assert row.paused_at is None
        assert row.pending_current_symbol is None
        assert row.pending_proposed_symbol is None
        assert row.pending_created_at is None


def test_first_boot_persists_session_state_via_get_or_create(
    sqlite_session_factory,
) -> None:
    build_service(sqlite_session_factory)

    with sqlite_session_factory() as session:
        # Exactly one row exists.
        assert session.scalar(select(func.count()).select_from(SessionState)) == 1


def test_first_boot_service_has_no_active_session_and_no_pending(
    sqlite_session_factory,
) -> None:
    service = build_service(sqlite_session_factory)

    assert service._active_session is None
    assert service._pending_replacement is None


# === Restart-survival: start_session


def test_restart_survives_start_session(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    seed_session_data(db_session)
    started = service1.start_session(db_session)
    db_session.commit()

    expected_symbol = started.lifecycle.current_pair_symbol
    expected_session_id = started.lifecycle.session_id
    assert expected_session_id is not None

    # Brand-new service instance → simulates a process restart against the
    # same DB.
    service2 = build_service(sqlite_session_factory)

    assert service2._active_session is not None
    assert service2._active_session.session_id == expected_session_id
    assert service2._active_session.current_pair_symbol == expected_symbol
    assert service2._active_session.started_at is not None
    assert service2._active_session.started_at.tzinfo is not None
    # paused_at is null right after start.
    assert service2._active_session.paused_at is None
    assert service2._pending_replacement is None


# === Restart-survival: pause / resume


def test_restart_survives_paused_state(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    seed_session_data(db_session)
    service1.start_session(db_session)
    service1.pause_session(db_session)
    db_session.commit()

    service2 = build_service(sqlite_session_factory)

    assert service2._active_session is not None
    assert service2._active_session.paused_at is not None
    assert service2._active_session.paused_at.tzinfo is not None


def test_restart_survives_pause_resume_cycle(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    seed_session_data(db_session)
    service1.start_session(db_session)
    service1.pause_session(db_session)
    service1.resume_session(db_session)
    db_session.commit()

    service2 = build_service(sqlite_session_factory)

    assert service2._active_session is not None
    # resume_session must have cleared ``paused_at`` on disk.
    assert service2._active_session.paused_at is None


# === complete_session clears the row in DB


def test_complete_session_clears_active_session_in_db(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    seed_session_data(db_session)
    service1.start_session(db_session)
    service1.complete_session(db_session)
    db_session.commit()

    # Restart and assert that in-memory state is fully cleared.
    service2 = build_service(sqlite_session_factory)
    assert service2._active_session is None
    assert service2._pending_replacement is None

    # And the DB row reflects the cleared state.
    with sqlite_session_factory() as session:
        row = session.get(SessionState, 1)
        assert row is not None
        assert row.session_id is None
        assert row.current_pair_symbol is None
        assert row.current_signal_id is None
        assert row.strategy_mode is None
        assert row.started_at is None
        assert row.paused_at is None
        assert row.pending_replacement_id is None
        assert row.pending_current_symbol is None
        assert row.pending_proposed_symbol is None
        assert row.pending_created_at is None


# === pair replacement


def test_restart_survives_review_pair_replacement(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    seed_session_data(db_session)
    started = service1.start_session(db_session)
    current_symbol = started.lifecycle.current_pair_symbol
    proposed_symbol = "SOLUSDT" if current_symbol != "SOLUSDT" else "BTCUSDT"

    review = service1.review_pair_replacement(db_session, proposed_symbol=proposed_symbol)
    db_session.commit()

    service2 = build_service(sqlite_session_factory)

    # Active session restored, pending replacement restored, in-memory
    # current_pair_symbol NOT yet updated (apply was not called).
    assert service2._active_session is not None
    assert service2._active_session.current_pair_symbol == current_symbol
    assert service2._pending_replacement is not None
    assert service2._pending_replacement.review_id == review.review_id
    assert service2._pending_replacement.proposed_symbol == proposed_symbol


def test_apply_pair_replacement_clears_pending_in_db(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    seed_session_data(db_session)
    started = service1.start_session(db_session)
    current_symbol = started.lifecycle.current_pair_symbol
    proposed_symbol = "SOLUSDT" if current_symbol != "SOLUSDT" else "BTCUSDT"

    review = service1.review_pair_replacement(db_session, proposed_symbol=proposed_symbol)
    service1.apply_pair_replacement(db_session, review.review_id)
    db_session.commit()

    # DB: pending_* cleared, current_pair_symbol updated.
    with sqlite_session_factory() as session:
        row = session.get(SessionState, 1)
        assert row is not None
        assert row.current_pair_symbol == proposed_symbol
        assert row.pending_replacement_id is None
        assert row.pending_current_symbol is None
        assert row.pending_proposed_symbol is None
        assert row.pending_created_at is None

    # In-memory: same.
    service2 = build_service(sqlite_session_factory)
    assert service2._active_session is not None
    assert service2._active_session.current_pair_symbol == proposed_symbol
    assert service2._pending_replacement is None


# === strategy_mode is restored (not to be confused with strategy_state / A5)


def test_strategy_mode_is_restored(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    seed_session_data(db_session)
    started = service1.start_session(db_session)
    expected_strategy_mode = started.briefing.active_strategy
    db_session.commit()

    service2 = build_service(sqlite_session_factory)

    assert service2._active_session is not None
    assert service2._active_session.strategy_mode == expected_strategy_mode
    # Sanity: this is the active-session snapshot, NOT the validation-lab
    # strategy_state (which is a different A5-scope column).
    assert expected_strategy_mode  # non-empty


# === TZ-aware round-trip (A2.5)


def test_paused_at_is_tz_aware_after_round_trip(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    seed_session_data(db_session)
    service1.start_session(db_session)
    service1.pause_session(db_session)
    db_session.commit()

    service2 = build_service(sqlite_session_factory)

    assert service2._active_session is not None
    assert service2._active_session.paused_at is not None
    assert service2._active_session.paused_at.tzinfo is not None
    assert service2._active_session.paused_at.tzinfo == UTC


# === Multiple restarts accumulate changes


def test_multiple_restarts_preserve_full_lifecycle(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    seed_session_data(db_session)
    started = service1.start_session(db_session)
    current_symbol = started.lifecycle.current_pair_symbol
    proposed_symbol = "SOLUSDT" if current_symbol != "SOLUSDT" else "BTCUSDT"

    review = service1.review_pair_replacement(db_session, proposed_symbol=proposed_symbol)
    service1.apply_pair_replacement(db_session, review.review_id)
    service1.pause_session(db_session)
    service1.resume_session(db_session)
    db_session.commit()

    service2 = build_service(sqlite_session_factory)
    snapshot = service2.build_snapshot(db_session)
    # Active session fields restored across the full lifecycle.
    assert snapshot.lifecycle.session_id is not None
    assert snapshot.lifecycle.current_pair_symbol == proposed_symbol
    assert snapshot.lifecycle.paused_at is None
    # NOTE: ``lifecycle_state`` is intentionally NOT asserted here.
    # ``runtime_manager`` is in-memory only (out of A4 scope; A6
    # reconciliation) so a fresh service on restart defaults to
    # ``BACKGROUND_MONITORING`` and ``_build_lifecycle`` reports
    # ``"review"`` — see A4 §6 Q2 in the report. Active-session fields
    # above are the real persistence contract.


# === lifecycle fields after restart (NOT lifecycle_state — see note above)


def test_lifecycle_fields_after_restart(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    seed_session_data(db_session)
    service1.start_session(db_session)
    db_session.commit()

    # Restart and assert that the lifecycle fields populated by the
    # restored in-memory state are present. ``lifecycle_state`` itself
    # is not asserted (see ``test_multiple_restarts_preserve_full_lifecycle``
    # for why). ``started_at`` and ``paused_at`` are serialized to ``str``
    # in the snapshot, so tz-aware checks belong on the service's
    # in-memory record (see ``test_paused_at_is_tz_aware_after_round_trip``).
    service2 = build_service(sqlite_session_factory)
    snapshot = service2.build_snapshot(db_session)
    assert snapshot.lifecycle.session_id is not None
    assert snapshot.lifecycle.current_pair_symbol is not None
    # In-memory record: started_at is a tz-aware datetime (A2.5).
    assert service2._active_session is not None
    assert service2._active_session.started_at is not None
    assert service2._active_session.started_at.tzinfo is not None


# === sanity: SessionState ORM exposes all 10 expected columns (defensive)


def test_typing_session_state_columns() -> None:
    """All 10 ``SessionState`` columns are declared in the model. This
    pins down the schema so a future field rename cannot silently break
    the wiring."""
    from clay.db.models_ops import SessionState as Model

    expected = {
        "id",
        "session_id",
        "current_pair_symbol",
        "current_signal_id",
        "strategy_mode",
        "started_at",
        "paused_at",
        "pending_replacement_id",
        "pending_current_symbol",
        "pending_proposed_symbol",
        "pending_created_at",
    }
    assert expected.issubset(set(Model.__annotations__.keys()))
    assert cast(type, Model) is SessionState


# === A4 follow-up #2: discriminator consistency for pending_created_at


def test_restore_pending_with_null_created_at_raises(
    sqlite_session_factory: sessionmaker,
) -> None:
    """A4 follow-up #2: ``pending_replacement_id`` is set (discriminator)
    but ``pending_created_at`` is NULL → ``ValueError`` on init
    (fail-fast), not a silent fallback to ``datetime.now(UTC)``.

    The other pending_* fields (current/proposed symbol) already raise
    in this configuration; this test pins down that ``pending_created_at``
    follows the same rule after the A4 follow-up micro-fix.
    """
    with sqlite_session_factory() as session:
        repo = SessionStateRepository(session)
        repo.get_or_create()  # ensure id=1 row exists
        repo.save(
            pending_replacement_id="rep-corrupt",
            pending_current_symbol="BTCUSDT",
            pending_proposed_symbol="ETHUSDT",
            # pending_created_at deliberately omitted → NULL
        )
        session.commit()

    with pytest.raises(ValueError, match="pending_created_at is NULL"):
        build_service(sqlite_session_factory)
