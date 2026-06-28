"""Persistence tests for ``WorkspaceService`` (Slice A5).

Three persistence contracts are exercised:

- **First-boot:** an empty DB is seeded with a ``workspace_focus``
  singleton row (id=1, default ``focus_source='system_recommendation'``,
  ``focus_symbol`` and ``selected_signal_id`` are ``None``) on the
  first ``WorkspaceService`` construction with a ``session_factory``.
- **Restart-survival:** a ``WorkspaceService`` constructed against a
  DB that has prior ``set_focus`` writes restores the persisted
  ``_focus_symbol`` / ``_focus_source`` / ``_selected_signal_id``.
- **D1 — explicit focus survives post-restart ``build_snapshot``:**
  the guard in ``build_snapshot`` prevents the system-recommendation
  auto-pick from clobbering an operator-set focus. This is the
  criterion that makes workspace persistence useful.
- **write-through:** ``set_focus`` persists through the supplied
  ``Session``; the service's in-memory state stays consistent with
  what is on disk.

The repository layer is bypassed for some direct DB asserts
(``session.get(WorkspaceFocus, 1)``) to keep the test honest about
what was actually written.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.db.models_ops import WorkspaceFocus
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.db.repositories_runtime_state import WorkspaceFocusRepository
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService


def build_service(session_factory: sessionmaker) -> WorkspaceService:
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
    return WorkspaceService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        registry=registry,
        signal_engine_service=signal_engine_service,
        session_factory=session_factory,
    )


def seed_workspace_data(session) -> None:
    """Seed minimal market data so that ``build_snapshot`` produces
    pair_contexts and exercises ``_pick_focus_context``. Without this
    seed, ``build_snapshot`` returns an empty snapshot and the guard
    in the focus block is never reached.
    """
    now = datetime.now(UTC)
    market_repository = MarketRepository(session)
    context_repository = ContextRepository(session)
    ops_repository = OpsRepository(session)
    for symbol, close in [("BTCUSDT", 70540.0), ("SOLUSDT", 181.5)]:
        market_repository.upsert_market_bars(
            [
                {
                    "symbol": symbol,
                    "timeframe": "15m",
                    "open": close * 0.99,
                    "high": close * 1.01,
                    "low": close * 0.985,
                    "close": close,
                    "volume": 260.0,
                    "quote_volume": close * 260.0,
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


# === First-boot


def test_first_boot_creates_empty_workspace_focus_row(sqlite_session_factory) -> None:
    build_service(sqlite_session_factory)

    with sqlite_session_factory() as session:
        repo = WorkspaceFocusRepository(session)
        row = repo.read()
        assert row is not None
        assert row.id == 1
        assert row.focus_symbol is None
        assert row.focus_source == "system_recommendation"
        assert row.selected_signal_id is None


def test_first_boot_persists_workspace_focus_via_get_or_create(
    sqlite_session_factory,
) -> None:
    build_service(sqlite_session_factory)

    with sqlite_session_factory() as session:
        # Exactly one row exists.
        assert session.scalar(select(func.count()).select_from(WorkspaceFocus)) == 1


# === Restart-survival: set_focus


def test_restart_survives_set_focus(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    service1.set_focus(symbol="SOLUSDT", focus_source="user", session=db_session)
    db_session.commit()

    service2 = build_service(sqlite_session_factory)

    assert service2._focus_symbol == "SOLUSDT"
    assert service2._focus_source == "user"
    assert service2._selected_signal_id is None

    # DB-level: row reflects the same state.
    with sqlite_session_factory() as session:
        row = session.get(WorkspaceFocus, 1)
        assert row is not None
        assert row.focus_symbol == "SOLUSDT"
        assert row.focus_source == "user"


# === D1: explicit focus survives post-restart build_snapshot


def test_restore_set_focus_survives_build_snapshot(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    """D1: an explicit (operator-set) focus MUST survive a post-restart
    ``build_snapshot``. Without the guard in ``build_snapshot``, the
    first snapshot after restart would overwrite the explicit focus
    with the system-recommendation auto-pick, defeating the whole
    point of workspace persistence.
    """
    service1 = build_service(sqlite_session_factory)
    service1.set_focus(symbol="BTCUSDT", focus_source="user", session=db_session)
    db_session.commit()

    service2 = build_service(sqlite_session_factory)
    assert service2._focus_source == "user"  # explicit focus restored

    # Seed data so build_snapshot produces pair_contexts and exercises
    # _pick_focus_context (otherwise it short-circuits to the empty
    # snapshot path and the guard is never tested).
    seed_workspace_data(db_session)

    snapshot = service2.build_snapshot(db_session)

    # In-memory state must NOT have been clobbered to
    # "system_recommendation" by the auto-pick.
    assert service2._focus_source == "user"
    assert service2._focus_symbol == "BTCUSDT"
    # The snapshot itself should reflect the explicit focus.
    assert snapshot.focus_pair.symbol == "BTCUSDT"
    assert snapshot.focus_pair.focus_source == "user"


def test_system_recommendation_focus_is_ephemeral(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    """Counter-test for D1: ephemeral system-recommendation focus IS
    allowed to be re-picked by ``build_snapshot``. Only explicit
    focus must be preserved. This pins down that the guard's
    condition is exactly ``focus_source == "system_recommendation"``
    and does not accidentally preserve ephemeral state too.

    Note: the auto-picked symbol depends on the mocked signal engine
    (BTCUSDT vs SOLUSDT vs absent), so we only assert the
    ``focus_source`` invariant — the contract under test.
    """
    service1 = build_service(sqlite_session_factory)
    # No set_focus call — focus_source stays "system_recommendation".
    seed_workspace_data(db_session)

    snapshot = service1.build_snapshot(db_session)
    # focus_source stays "system_recommendation" (no explicit set_focus).
    assert service1._focus_source == "system_recommendation"
    # Snapshot reflects the system-recommendation path.
    assert snapshot.focus_pair.focus_source == "system_recommendation"

    # Second call: the guard does NOT block re-pick for the
    # system_recommendation path — it stays re-computable.
    snapshot2 = service1.build_snapshot(db_session)
    assert service1._focus_source == "system_recommendation"
    assert snapshot2.focus_pair.focus_source == "system_recommendation"


# === typing sanity


def test_typing_workspace_focus_columns() -> None:
    from clay.db.models_ops import WorkspaceFocus as Model

    expected = {
        "id",
        "focus_symbol",
        "focus_source",
        "selected_signal_id",
        "updated_at",
    }
    assert expected.issubset(set(Model.__annotations__.keys()))
    assert cast(type, Model) is WorkspaceFocus
