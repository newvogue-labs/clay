"""Tests for D-15: halt-latch mode probe."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from clay.db import models_orders  # noqa: F401 — register tables
from clay.db.base import Base
from clay.db.session import SQLITE_SCHEMA_TRANSLATE_MAP
from clay.execution.ledger.halt_latch import HaltLatchRepository
from clay.execution.ledger.halt_probe import build_halt_latch_mode_probe
from clay.execution.proof.snapshot import SessionMode


def _make_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": SQLITE_SCHEMA_TRANSLATE_MAP},
    )


@pytest.fixture()
def session_factory():
    """In-memory SQLite session factory."""
    engine = _make_engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


class TestHaltLatchModeProbe:
    def test_engaged_returns_halted(self, session_factory) -> None:
        """Latch engaged → SessionMode.HALTED."""
        # Engage the latch
        with session_factory() as s:
            repo = HaltLatchRepository(s)
            repo.engage(reason="test_fatal", now=datetime.now(UTC))
            s.commit()

        probe = build_halt_latch_mode_probe(session_factory)
        assert probe() == SessionMode.HALTED

    def test_clean_returns_normal(self, session_factory) -> None:
        """Latch not engaged → SessionMode.NORMAL."""
        probe = build_halt_latch_mode_probe(session_factory)
        assert probe() == SessionMode.NORMAL

    def test_no_latch_row_returns_normal(self, session_factory) -> None:
        """No latch row at all → SessionMode.NORMAL (is_engaged returns False)."""
        probe = build_halt_latch_mode_probe(session_factory)
        assert probe() == SessionMode.NORMAL

    def test_exception_propagates(self) -> None:
        """Exception in session → propagates (gate fail-closes to HALTED)."""
        from sqlalchemy.pool import NullPool

        bad_engine = create_engine(
            "sqlite://",
            poolclass=NullPool,
        )
        bad_factory = sessionmaker(bind=bad_engine)

        probe = build_halt_latch_mode_probe(bad_factory)
        with pytest.raises(Exception):
            probe()
