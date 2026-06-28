"""Regression tests for the demo signal seed harness.

Hermetic SQLite (via the project's ``db_session`` fixture). Each
test gets a fresh DB. The two tests prove the seam from G5b:

* ``seed`` produces a signal with ``state in {"active", "weakening"}``
  and ``ranking_score >= 0.45`` on the real signal_engine pipeline.
* ``seed`` is idempotent (re-running does not drift the score) and
  ``clean`` removes the seeded rows so the signal disappears.
"""

from __future__ import annotations

from typing import cast

from scripts.seed_demo_signal_data import clean, seed

from tests.signal_engine.test_signal_engine_service import build_signal_engine


def test_seed_produces_eligible_ranked_signal(db_session) -> None:
    """After seeding, the real signal_engine returns >=1 weakening/active
    signal with ranking_score >= 0.45."""
    trackers = seed(db_session, ["SOLUSDT"])

    engine = build_signal_engine()
    snapshot = engine.build_snapshot(db_session)

    assert snapshot.signals, "seed should produce at least one signal"
    sol = next(signal for signal in snapshot.signals if signal.symbol == "SOLUSDT")
    assert sol.state in {"active", "weakening"}, (
        f"expected active/weakening, got {sol.state!r} "
        f"(ranking_score={sol.ranking_score}, response_action={sol.response_action})"
    )
    assert sol.ranking_score >= 0.45, (
        f"ranking_score {sol.ranking_score} should clear the weakening threshold"
    )
    assert cast(int, len(trackers.bar_keys)) == 50
    # One freshness row per configured timeframe (5m, 15m, 1h), so the
    # ``build_shortlist_metrics`` iteration that overwrites stale rows
    # still ends up with ``fresh`` for the symbol.
    assert cast(int, len(trackers.freshness_keys)) == 3


def test_seed_is_idempotent_and_cleanable(db_session) -> None:
    """Re-running seed does not drift the score; clean removes the rows
    so the signal pipeline reverts to the empty-state baseline."""
    engine = build_signal_engine()

    seed(db_session, ["SOLUSDT"])
    snapshot_1 = engine.build_snapshot(db_session)
    sol_1 = next(signal for signal in snapshot_1.signals if signal.symbol == "SOLUSDT")

    # Re-seed (idempotent path). The repo upserts keep row count at 1
    # per bar key and 1 freshness row; the seed returns a fresh tracker.
    trackers_2 = seed(db_session, ["SOLUSDT"])
    snapshot_2 = engine.build_snapshot(db_session)
    sol_2 = next(signal for signal in snapshot_2.signals if signal.symbol == "SOLUSDT")

    assert sol_2.ranking_score == sol_1.ranking_score, (
        f"re-seed should not drift the score: {sol_1.ranking_score} -> {sol_2.ranking_score}"
    )
    assert sol_2.state == sol_1.state

    # Clean using the second tracker; the first seed is a subset of the
    # second (same keys, same shape), so this also exercises the case
    # where a previous tracker was orphaned.
    removed = clean(db_session, trackers_2)
    assert removed > 0, "clean should have removed at least the rows just inserted"

    # After clean, no SOLUSDT signal with state in {active, weakening}.
    snapshot_3 = engine.build_snapshot(db_session)
    sol_3 = next(
        (signal for signal in snapshot_3.signals if signal.symbol == "SOLUSDT"),
        None,
    )
    if sol_3 is not None:
        assert sol_3.state not in {"active", "weakening"}, (
            f"after clean the signal should revert; got state={sol_3.state!r}, "
            f"ranking_score={sol_3.ranking_score}"
        )
    else:
        # No signal at all is also a valid "reverted" outcome.
        pass

    # Clean again on the now-empty DB: idempotent (0 rows removed is acceptable).
    removed_2 = clean(db_session, trackers_2)
    assert removed_2 == 0, "second clean on an empty seed set should remove 0 rows"
