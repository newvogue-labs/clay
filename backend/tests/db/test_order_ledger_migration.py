"""Tests for order-ledger migration (0026) and model parity.

Round-trip: upgrade → 3 tables exist; downgrade → 3 tables gone.
Parity: column names, PKs, and UNIQUE constraints match between
Base.metadata (ORM models) and the create_all schema.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from collections.abc import Generator
from typing import Protocol, runtime_checkable

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Inspector, create_engine, inspect, text
from sqlalchemy.engine import Engine

from clay.db.base import Base
from clay.db.session import SQLITE_SCHEMA_TRANSLATE_MAP

# Импорт моделей чтобы Base.metadata видел таблицы
from clay.db import models_orders  # noqa: F401

ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"
MIGRATION_FILE = ALEMBIC_DIR / "versions" / "0026_order_ledger_schema.py"

EXPECTED_TABLES = frozenset({"order_events", "order_current_state", "fills"})


@runtime_checkable
class _MigrationModule(Protocol):
    def upgrade(self) -> None: ...
    def downgrade(self) -> None: ...


def _load_migration() -> _MigrationModule:
    spec = spec_from_file_location("migration_0026", MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod  # type: ignore[return-value]


def _make_sqlite_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": SQLITE_SCHEMA_TRANSLATE_MAP},
    )


# ---------------------------------------------------------------------------
# Round-trip migration on SQLite (direct function calls, no env.py)
# ---------------------------------------------------------------------------


class TestMigrationRoundTrip:
    def test_upgrade_creates_three_tables(self) -> None:
        migration = _load_migration()
        engine = _make_sqlite_engine()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            assert EXPECTED_TABLES.issubset(tables), (
                f"missing: {EXPECTED_TABLES - tables}"
            )
        engine.dispose()

    def test_downgrade_removes_three_tables(self) -> None:
        migration = _load_migration()
        engine = _make_sqlite_engine()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
                migration.downgrade()

            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            assert EXPECTED_TABLES.isdisjoint(tables), (
                f"tables still present after downgrade: {EXPECTED_TABLES & tables}"
            )
        engine.dispose()

    def test_upgrade_downgrade_no_errors(self) -> None:
        """Full cycle: upgrade → downgrade should not raise."""
        migration = _load_migration()
        engine = _make_sqlite_engine()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
                migration.downgrade()
        engine.dispose()


# ---------------------------------------------------------------------------
# Parity: ORM models vs create_all schema
# ---------------------------------------------------------------------------


def _get_columns(inspector: Inspector, table: str) -> dict[str, str]:
    return {col["name"]: str(col["type"]) for col in inspector.get_columns(table)}


def _get_pk_columns(inspector: Inspector, table: str) -> frozenset[str]:
    pk = inspector.get_pk_constraint(table)
    return frozenset(pk["constrained_columns"]) if pk else frozenset()


def _get_unique_constraints(inspector: Inspector, table: str) -> list[frozenset[str]]:
    return [
        frozenset(uq["column_names"]) for uq in inspector.get_unique_constraints(table)
    ]


class TestModelParity:
    """Verify ORM models match create_all schema (no schema prefix on SQLite)."""

    @pytest.fixture()
    def inspector(self) -> Generator[Inspector, None, None]:
        engine = _make_sqlite_engine()
        Base.metadata.create_all(engine)
        insp = inspect(engine)
        yield insp
        engine.dispose()

    def _model_columns(self, table_name: str) -> dict[str, str]:
        table = Base.metadata.tables[f"ops.{table_name}"]
        return {col.name: str(col.type) for col in table.columns}

    def _model_pk(self, table_name: str) -> frozenset[str]:
        table = Base.metadata.tables[f"ops.{table_name}"]
        return frozenset(col.name for col in table.primary_key.columns)

    # -- order_events --

    def test_order_events_column_names(self, inspector: Inspector) -> None:
        model_cols = set(self._model_columns("order_events"))
        db_cols = set(_get_columns(inspector, "order_events").keys())
        assert model_cols == db_cols

    def test_order_events_pk(self, inspector: Inspector) -> None:
        assert self._model_pk("order_events") == {"ledger_seq"}
        assert _get_pk_columns(inspector, "order_events") == {"ledger_seq"}

    def test_order_events_event_id_unique(self, inspector: Inspector) -> None:
        uniques = _get_unique_constraints(inspector, "order_events")
        assert any("event_id" in uq for uq in uniques)

    # -- order_current_state --

    def test_order_current_state_column_names(self, inspector: Inspector) -> None:
        model_cols = set(self._model_columns("order_current_state"))
        db_cols = set(_get_columns(inspector, "order_current_state").keys())
        assert model_cols == db_cols

    def test_order_current_state_pk(self, inspector: Inspector) -> None:
        assert self._model_pk("order_current_state") == {"client_order_id"}
        assert _get_pk_columns(inspector, "order_current_state") == {"client_order_id"}

    # -- fills --

    def test_fills_column_names(self, inspector: Inspector) -> None:
        model_cols = set(self._model_columns("fills"))
        db_cols = set(_get_columns(inspector, "fills").keys())
        assert model_cols == db_cols

    def test_fills_pk(self, inspector: Inspector) -> None:
        assert self._model_pk("fills") == {"fill_pk"}
        assert _get_pk_columns(inspector, "fills") == {"fill_pk"}

    def test_fills_venue_trade_id_unique(self, inspector: Inspector) -> None:
        uniques = _get_unique_constraints(inspector, "fills")
        assert any(uq == frozenset({"venue", "trade_id"}) for uq in uniques)


# ---------------------------------------------------------------------------
# INSERT coverage: auto-increment PKs on SQLite
# ---------------------------------------------------------------------------


class TestInsertAutoIncrement:
    """Verify that auto-increment PKs (ledger_seq, fill_pk) work on SQLite.

    Would fail on bare ``BigInteger`` PK (no rowid alias) —
    the ``with_variant(Integer, "sqlite")`` fix makes this pass.
    """

    def test_order_events_ledger_seq_autoincrement(self) -> None:
        migration = _load_migration()
        engine = _make_sqlite_engine()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

            # INSERT без явного ledger_seq
            conn.execute(
                text(
                    "INSERT INTO order_events "
                    "(event_id, client_order_id, venue, symbol, event_type, "
                    "payload, created_at) "
                    "VALUES ('ev-001', 'cid-001', 'binance', 'BTC/USDT', "
                    "'intent', '{}', '2026-01-01T00:00:00Z')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO order_events "
                    "(event_id, client_order_id, venue, symbol, event_type, "
                    "payload, created_at) "
                    "VALUES ('ev-002', 'cid-002', 'binance', 'BTC/USDT', "
                    "'intent', '{}', '2026-01-01T00:00:01Z')"
                )
            )
            conn.commit()

            rows = conn.execute(
                text(
                    "SELECT ledger_seq, event_id FROM order_events ORDER BY ledger_seq"
                )
            ).fetchall()
            assert len(rows) == 2
            # ledger_seq заполнился автоматически
            assert rows[0][0] is not None
            assert rows[1][0] is not None
            # монотонно растёт
            assert rows[1][0] > rows[0][0]
        engine.dispose()

    def test_fills_fill_pk_autoincrement(self) -> None:
        migration = _load_migration()
        engine = _make_sqlite_engine()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

            conn.execute(
                text(
                    "INSERT INTO fills "
                    "(venue, trade_id, venue_order_id, symbol, side, "
                    "quantity, price, created_at) "
                    "VALUES ('binance', 't-001', 'vo-001', 'BTC/USDT', "
                    "'buy', '0.001', '50000', '2026-01-01T00:00:00Z')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO fills "
                    "(venue, trade_id, venue_order_id, symbol, side, "
                    "quantity, price, created_at) "
                    "VALUES ('binance', 't-002', 'vo-002', 'BTC/USDT', "
                    "'buy', '0.002', '51000', '2026-01-01T00:00:01Z')"
                )
            )
            conn.commit()

            rows = conn.execute(
                text("SELECT fill_pk, trade_id FROM fills ORDER BY fill_pk")
            ).fetchall()
            assert len(rows) == 2
            assert rows[0][0] is not None
            assert rows[1][0] is not None
            assert rows[1][0] > rows[0][0]
        engine.dispose()
