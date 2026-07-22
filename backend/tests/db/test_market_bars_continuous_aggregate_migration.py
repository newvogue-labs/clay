"""Smoke-test for 0031_market_bars_continuous_aggregate migration on SQLite.

Verifies that the SQLite guard in upgrade()/downgrade() makes them
no-ops — no timescale-SQL is executed, no errors raised.  Also
asserts the migration module's revision chain points to 0030.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Protocol, runtime_checkable

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine


ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"
MIGRATION_FILE = ALEMBIC_DIR / "versions" / "0031_market_bars_continuous_aggregate.py"


@runtime_checkable
class _MigrationModule(Protocol):
    revision: str
    down_revision: str | None

    def upgrade(self) -> None: ...
    def downgrade(self) -> None: ...


def _load_migration() -> _MigrationModule:
    spec = spec_from_file_location("migration_0031", MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod  # type: ignore[return-value]


def _make_sqlite_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )


class TestMigrationChain:
    def test_revision_is_0031(self) -> None:
        mod = _load_migration()
        assert getattr(mod, "revision") == "0031_market_bars_cagg"

    def test_down_revision_is_0030(self) -> None:
        mod = _load_migration()
        assert getattr(mod, "down_revision") == "0030_market_bars_retention"


class TestSqliteGuard:
    """upgrade/downgrade must be no-ops on SQLite (dialect guard)."""

    def test_upgrade_noop_on_sqlite(self) -> None:
        migration = _load_migration()
        engine = _make_sqlite_engine()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()  # must not raise
        engine.dispose()

    def test_downgrade_noop_on_sqlite(self) -> None:
        migration = _load_migration()
        engine = _make_sqlite_engine()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()  # must not raise
        engine.dispose()

    def test_round_trip_noop_on_sqlite(self) -> None:
        migration = _load_migration()
        engine = _make_sqlite_engine()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
                migration.downgrade()
        engine.dispose()

    def test_no_tables_created_on_sqlite(self) -> None:
        """Guard returns before touching the DB — nothing created."""
        migration = _load_migration()
        engine = _make_sqlite_engine()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            assert "market_bars_1d" not in tables
        engine.dispose()
