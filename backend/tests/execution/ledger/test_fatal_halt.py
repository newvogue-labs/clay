"""Tests for D-12d D5: wire FATAL→halt (broad-halt)."""

from __future__ import annotations


import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from clay.db import models_orders  # noqa: F401 — register tables
from clay.db.base import Base
from clay.db.session import SQLITE_SCHEMA_TRANSLATE_MAP
from clay.execution.ledger.fatal_halt import FatalHaltWiring
from clay.execution.ledger.reconcile import (
    Mismatch,
    ReconcileMismatchKind,
    ReconcileReport,
)


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


@pytest.fixture()
def wiring(session_factory):
    """FatalHaltWiring with a fresh session."""
    return FatalHaltWiring(session_factory=session_factory)


class TestFatalHaltWiring:
    def test_fatal_engages_latch(
        self, session_factory, wiring: FatalHaltWiring
    ) -> None:
        """Fatal report → latch engaged."""
        report = ReconcileReport(
            mismatches=[
                Mismatch(
                    kind=ReconcileMismatchKind.ILLEGAL_DRIFT,
                    client_order_id="cid-001",
                    venue_order_id="void-001",
                    detail="state drift",
                )
            ]
        )

        result = wiring.on_fatal_report(report, venue="bybit", symbol="BTCUSDT")

        assert result is True

        # Verify latch is engaged
        from clay.execution.ledger.halt_latch import HaltLatchRepository

        with session_factory() as s:
            repo = HaltLatchRepository(s)
            assert repo.is_engaged() is True

    def test_clean_report_does_not_engage(
        self, session_factory, wiring: FatalHaltWiring
    ) -> None:
        """Clean report → latch not engaged."""
        report = ReconcileReport()

        result = wiring.on_fatal_report(report, venue="bybit", symbol="BTCUSDT")

        assert result is False

        from clay.execution.ledger.halt_latch import HaltLatchRepository

        with session_factory() as s:
            repo = HaltLatchRepository(s)
            assert repo.is_engaged() is False

    def test_escalated_fatal_engages_latch(
        self, session_factory, wiring: FatalHaltWiring
    ) -> None:
        """Age-escalated UNKNOWNs → latch engaged."""
        result = wiring.on_escalated_fatal(
            venue="bybit",
            symbol="BTCUSDT",
            escalated_cids=["cid-001", "cid-002"],
        )

        assert result is True

        from clay.execution.ledger.halt_latch import HaltLatchRepository

        with session_factory() as s:
            repo = HaltLatchRepository(s)
            assert repo.is_engaged() is True

    def test_empty_escalated_does_not_engage(
        self, session_factory, wiring: FatalHaltWiring
    ) -> None:
        """Empty escalated list → latch not engaged."""
        result = wiring.on_escalated_fatal(
            venue="bybit",
            symbol="BTCUSDT",
            escalated_cids=[],
        )

        assert result is False

    def test_writes_reason_to_latch(
        self, session_factory, wiring: FatalHaltWiring
    ) -> None:
        """Fatal report writes reason to latch."""
        report = ReconcileReport(
            mismatches=[
                Mismatch(
                    kind=ReconcileMismatchKind.ILLEGAL_DRIFT,
                    client_order_id="cid-001",
                    venue_order_id="void-001",
                    detail="state drift",
                )
            ]
        )

        wiring.on_fatal_report(report, venue="bybit", symbol="BTCUSDT")

        from clay.execution.ledger.halt_latch import HaltLatchRepository

        with session_factory() as s:
            repo = HaltLatchRepository(s)
            latch = repo.get_latch()
            assert latch is not None
            assert latch.engaged is True
            assert latch.reason is not None
            assert "illegal_drift" in latch.reason
            assert "bybit" in latch.reason
