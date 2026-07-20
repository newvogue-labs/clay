"""Tests for D-12d D4: durable halt-latch."""

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


def _make_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": SQLITE_SCHEMA_TRANSLATE_MAP},
    )


@pytest.fixture()
def session_factory():
    """In-memory SQLite session factory for halt-latch tests."""
    engine = _make_engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture()
def repo(session_factory):
    """HaltLatchRepository with a fresh session."""
    with session_factory() as s:
        yield HaltLatchRepository(s)


class TestHaltLatch:
    def test_initial_state_disengaged(self, repo: HaltLatchRepository) -> None:
        """Latch starts disengaged (or None → False)."""
        assert repo.is_engaged() is False

    def test_engage(self, repo: HaltLatchRepository) -> None:
        """Engage the latch → is_engaged True."""
        now = datetime.now(UTC)
        repo.engage(reason="fatal_mismatch", now=now)
        assert repo.is_engaged() is True

    def test_engage_idempotent(self, repo: HaltLatchRepository) -> None:
        """Double-engage is idempotent."""
        now = datetime.now(UTC)
        repo.engage(reason="fatal_mismatch", now=now)
        repo.engage(reason="fatal_mismatch", now=now)
        assert repo.is_engaged() is True

    def test_disengage(self, repo: HaltLatchRepository) -> None:
        """Disengage after engage → is_engaged False."""
        now = datetime.now(UTC)
        repo.engage(reason="fatal_mismatch", now=now)
        repo.disengage(reason="operator_reset", now=now)
        assert repo.is_engaged() is False

    def test_disengage_writes_audit(self, repo: HaltLatchRepository) -> None:
        """Disengage writes reset_at and reset_reason."""
        now = datetime.now(UTC)
        repo.engage(reason="fatal_mismatch", now=now)
        repo.disengage(reason="operator_reset", now=now)
        latch = repo.get_latch()
        assert latch is not None
        assert latch.reset_at == now
        assert latch.reset_reason == "operator_reset"

    def test_engage_writes_audit(self, repo: HaltLatchRepository) -> None:
        """Engage writes engaged_at and reason."""
        now = datetime.now(UTC)
        repo.engage(reason="fatal_mismatch", now=now)
        latch = repo.get_latch()
        assert latch is not None
        assert latch.engaged_at == now
        assert latch.reason == "fatal_mismatch"

    def test_restart_with_engaged_latch(self, repo: HaltLatchRepository) -> None:
        """Simulate restart: engage in one session, check in another."""
        now = datetime.now(UTC)
        repo.engage(reason="fatal_mismatch", now=now)
        # Simulate new session (new repo instance)
        session = repo.session
        new_repo = HaltLatchRepository(session)
        assert new_repo.is_engaged() is True

    def test_clean_tick_does_not_disengage(
        self, repo: HaltLatchRepository
    ) -> None:
        """A clean reconcile tick does NOT disengage the latch."""
        now = datetime.now(UTC)
        repo.engage(reason="fatal_mismatch", now=now)
        # Simulate clean tick — should not call disengage
        assert repo.is_engaged() is True
