"""Shared helpers for the A6 integration suite.

These helpers deliberately exercise the **production** ``build_services``
factory (not a parallel hand-rolled bundle). The whole point of A6 is
that the integration suite catches bootstrap regressions like the
double-init bug discovered during A6 recon — a parallel bundle
construction would test a different universe and miss exactly the
class of bug the suite is meant to catch.

The file-based SQLite path follows the existing conftest pattern
(``tmp_path / "clay-restart.db"``) so a real ``session_factory`` is
threaded through every persisted service. ``XdgPaths`` is rooted at
``tmp_path`` so ``AuditWriter`` and config files do not leak into
the developer's home directory.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from clay.bootstrap import build_services
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.db import Base, build_engine, build_session_factory
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.settings.ingestion import IngestionSettings


def make_xdg_paths(tmp_path: Path) -> XdgPaths:
    """Build an isolated ``XdgPaths`` rooted at ``tmp_path``."""
    return XdgPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
    )


def make_file_sqlite_settings(
    tmp_path: Path, db_filename: str = "clay-restart.db"
) -> IngestionSettings:
    """Build an ``IngestionSettings`` pointing at a file-based SQLite
    under ``tmp_path`` (NOT ``:memory:`` — A1-decisions: integration
    tests must exercise the real driver path)."""
    return IngestionSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / db_filename}",
        market_symbols=["BTCUSDT", "ETHUSDT"],
        market_timeframes=["5m", "15m"],
    )


def create_engine_and_schema(settings: IngestionSettings) -> Engine:
    """Create the engine and run ``Base.metadata.create_all`` so the
    same DB schema is materialised before the factory is called.

    The factory itself does NOT run DDL — it just opens sessions and
    lets the service ``__init__``s call their repository helpers. The
    schema is the caller's responsibility (this mirrors the production
    ``alembic upgrade head`` step that the bootstrap does NOT
    re-implement; tests get the schema via SQLAlchemy directly).
    """
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    return engine


def build_services_for_integration(
    tmp_path: Path,
    db_filename: str = "clay-restart.db",
) -> dict[str, Any]:
    """Build the full Clay service graph via the **production** factory
    on a file-based SQLite rooted at ``tmp_path``.

    The same ``ConfigLoader(XdgPaths(tmp_path))`` and
    ``build_session_factory(settings)`` plumbing is used here as
    production uses — only the *paths* differ. The integration suite
    therefore exercises the real wiring (catches future bootstrap
    regressions like the A6 double-init bug).

    Returns the factory's services dict. The caller can also open a
    session via ``services["session_factory"]()`` for DB mutations.
    """
    config_loader = ConfigLoader(make_xdg_paths(tmp_path))
    settings = make_file_sqlite_settings(tmp_path, db_filename=db_filename)
    create_engine_and_schema(settings)
    session_factory = build_session_factory(settings)
    return build_services(
        config_loader=config_loader,
        session_factory=session_factory,
    )


def seed_all_areas(session) -> None:
    """Seed the bare minimum so the operator-path services can build
    healthy preflight + brief snapshots (market fresh, context fresh,
    connectors healthy). Mirrors the ``seed_validation_inputs`` helper
    in ``test_validation_lab_persistence.py`` and the
    ``seed_alpha_inputs`` helper in ``test_alpha_readiness_service.py``,
    so the integration suite is consistent with the existing test
    contract: with this seed, ``session_control.start_session`` is
    allowed to succeed.
    """
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
                "headline": "Restart-survival integration input is ready",
                "summary": "Context supports a replay run.",
                "published_at": now - timedelta(minutes=30),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/restart",
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
    ops_repository.record_connector_status(
        connector_id="demo-sentiment",
        connector_type="sentiment",
        status="healthy",
        observed_at=now,
    )
    session.commit()
