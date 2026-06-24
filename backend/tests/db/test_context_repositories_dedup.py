"""C1 — dedup tests for ContextRepository.

Validates:
- SELECT-skip fast-path (existing rows short-circuit before INSERT)
- IntegrityError catch (race-condition dedup via DB UniqueConstraint)
- Savepoint isolation (outer session is not rolled back on duplicate)
- tuples stable return contract
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from clay.db.repositories_context import ContextRepository


def test_store_news_items_writes_new_row(db_session) -> None:
    repository = ContextRepository(db_session)
    observed_at = datetime(2026, 6, 3, 10, 0, tzinfo=UTC)

    written = repository.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "BTC holds breakout",
                "summary": "Constructive",
                "published_at": observed_at,
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/btc-breakout",
            },
        ],
    )
    db_session.commit()

    assert written == 1
    assert len(repository.latest_news()) == 1


def test_store_news_items_select_skip_short_circuits_before_insert(
    db_session,
) -> None:
    """Duplicate (source, headline, published_at) → SELECT hit → skip, no INSERT."""
    repository = ContextRepository(db_session)
    observed_at = datetime(2026, 6, 3, 11, 0, tzinfo=UTC)
    payload = {
        "source_name": "demo_news_feed",
        "headline": "BTC range-bound",
        "summary": "Calm",
        "published_at": observed_at,
        "symbol": "BTCUSDT",
        "source_url": "https://example.invalid/news/btc-range",
    }

    # First call: 1 written
    first = repository.store_news_items([payload])
    db_session.commit()
    assert first == 1

    # Second call with same key: SELECT-skip path (no IntegrityError expected)
    second = repository.store_news_items([payload])
    db_session.commit()

    assert second == 0  # dedup-skipped via SELECT, not via IntegrityError catch
    assert len(repository.latest_news()) == 1  # still exactly 1 row


def test_store_news_items_catches_integrity_error_on_race(
    db_session, caplog: pytest.LogCaptureFixture
) -> None:
    """Race scenario: SELECT returns None (concurrent insert), then INSERT raises
    IntegrityError. Must be caught via savepoint + flush, NOT bubble up."""
    repository = ContextRepository(db_session)
    observed_at = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)

    # Pre-seed a row that will collide (simulating concurrent writer)
    pre_existing_payload = {
        "source_name": "demo_news_feed",
        "headline": "BTC halts at resistance",
        "summary": "Rejected",
        "published_at": observed_at,
        "symbol": "BTCUSDT",
        "source_url": "https://example.invalid/news/btc-resistance",
    }
    repository.store_news_items([pre_existing_payload])
    db_session.commit()

    # Now: mock the SELECT to lie (return None) so the repository tries to INSERT
    # and hits the DB-level UNIQUE constraint. This simulates the TOCTOU race.
    original_scalar = db_session.scalar
    call_count = {"n": 0}

    def lying_scalar(*args, **kwargs):
        call_count["n"] += 1
        # First call (our SELECT for the new key) — return None
        # Subsequent calls (latest_news at the end) — passthrough
        result = original_scalar(*args, **kwargs)
        return None if call_count["n"] == 1 else result

    db_session.scalar = MagicMock(side_effect=lying_scalar)

    _logger = logging.getLogger("clay.context")
    _logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="clay.context"):
            written = repository.store_news_items([pre_existing_payload])

        db_session.scalar = original_scalar
        db_session.commit()

        # Must NOT raise — caught via savepoint
        assert written == 0
        # Verify log: dedup-skipped event
        assert any(
            "skipped duplicate news" in record.message
            for record in caplog.records
        )
        # Exactly 1 row in DB (no double-insert)
        assert len(repository.latest_news()) == 1
    finally:
        _logger.removeHandler(caplog.handler)


def test_store_news_items_savepoint_preserves_outer_session(db_session) -> None:
    """Savepoint rollback on duplicate must NOT kill the outer session.
    A subsequent INSERT in the same session must still commit successfully."""
    repository = ContextRepository(db_session)
    t0 = datetime(2026, 6, 3, 13, 0, tzinfo=UTC)
    t1 = datetime(2026, 6, 3, 13, 5, tzinfo=UTC)

    # Pre-seed: this row will be the "duplicate" that the racing INSERT collides with
    colliding = {
        "source_name": "demo_news_feed",
        "headline": "ETH rolls over",
        "summary": "Failed",
        "published_at": t0,
        "symbol": "ETHUSDT",
        "source_url": "https://example.invalid/news/eth-rollover",
    }
    repository.store_news_items([colliding])
    db_session.commit()

    # Mock SELECT to lie → forces INSERT attempt → IntegrityError path
    original_scalar = db_session.scalar
    call_count = {"n": 0}

    def lying_scalar(*args, **kwargs):
        call_count["n"] += 1
        result = original_scalar(*args, **kwargs)
        return None if call_count["n"] == 1 else result

    db_session.scalar = MagicMock(side_effect=lying_scalar)

    # 1) Attempt duplicate (will hit IntegrityError + savepoint rollback)
    repository.store_news_items([colliding])
    db_session.scalar = original_scalar

    # 2) New row in same session — must succeed
    new_row = {
        "source_name": "demo_news_feed",
        "headline": "SOL breakout",
        "summary": "Continuation",
        "published_at": t1,
        "symbol": "SOLUSDT",
        "source_url": "https://example.invalid/news/sol-breakout",
    }
    written = repository.store_news_items([new_row])
    db_session.commit()

    assert written == 1
    rows = repository.latest_news()
    assert len(rows) == 2  # colliding + new_row, NOT 3 (no double insert)


def test_store_sentiment_snapshots_writes_new_row(db_session) -> None:
    repository = ContextRepository(db_session)
    observed_at = datetime(2026, 6, 3, 14, 0, tzinfo=UTC)

    written = repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.68,
                "captured_at": observed_at,
            },
        ],
    )
    db_session.commit()

    assert written == 1
    assert len(repository.latest_sentiment()) == 1


def test_store_sentiment_snapshots_catches_integrity_error_on_race(
    db_session, caplog: pytest.LogCaptureFixture
) -> None:
    repository = ContextRepository(db_session)
    observed_at = datetime(2026, 6, 3, 15, 0, tzinfo=UTC)
    payload = {
        "source_name": "demo_sentiment_feed",
        "symbol": "BTCUSDT",
        "sentiment_label": "bullish",
        "sentiment_score": 0.71,
        "captured_at": observed_at,
    }

    # Pre-seed
    repository.store_sentiment_snapshots([payload])
    db_session.commit()

    # Force INSERT path despite existing row (TOCTOU race simulation)
    original_scalar = db_session.scalar
    call_count = {"n": 0}

    def lying_scalar(*args, **kwargs):
        call_count["n"] += 1
        result = original_scalar(*args, **kwargs)
        return None if call_count["n"] == 1 else result

    db_session.scalar = MagicMock(side_effect=lying_scalar)

    _logger = logging.getLogger("clay.context")
    _logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="clay.context"):
            written = repository.store_sentiment_snapshots([payload])

        db_session.scalar = original_scalar
        db_session.commit()

        assert written == 0
        assert any(
            "skipped duplicate sentiment" in record.message
            for record in caplog.records
        )
        assert len(repository.latest_sentiment()) == 1
    finally:
        _logger.removeHandler(caplog.handler)
