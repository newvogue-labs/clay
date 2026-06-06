"""Seed the demo signal pipeline so the FSM gate can pass.

Writes the minimum input rows that ``signal_engine.build_snapshot``
needs to produce a ranked signal with state in
``{"active", "weakening"}`` on the live ``clay`` DB. Used by G5b for
the 5-session smoke and as the regression target of the test in
``tests/scripts/test_seed_demo_signal_data.py``.

**Q5 guardrails (load-bearing):**

* Writes ONLY to ``market.market_bars``, ``market.market_freshness_status``,
  ``context.news_items``, ``context.sentiment_snapshots``,
  ``ops.connector_status_history``. Nothing else.
* Does NOT touch ``ops.session_state`` (FSM is operator-driven).
* Does NOT call any service / route / API method.
* Does NOT touch ``demo.demo_trade_records`` or
  ``validation.validation_runs`` (Q5 manual-only).
* Does NOT make any exchange / network call.

**Idempotency:**

* ``market_bars`` -- upsert keyed on
  ``(source, symbol, timeframe, bar_open_time)`` (in
  ``MarketRepository.upsert_market_bars``).
* ``market_freshness_status`` -- upsert keyed on
  ``(source, symbol, timeframe)``.
* ``context.news_items`` / ``context.sentiment_snapshots`` --
  SELECT-skip + UniqueConstraint fallback (in repos).
* ``connector_status_history`` -- append-only by table design; the
  effect is idempotent (latest per ``connector_id`` is what the
  pipeline reads via ``OpsRepository.latest_connector_statuses``).
  The seed uses a unique ``connector_id`` (``binance_spot_seed``) so
  teardown can target exactly the rows we inserted without
  interfering with other operational connectors.

**Freshness on read:** ``build_shortlist_metrics`` re-derives
``availability_status`` from
``resolve_market_freshness_status(stored_status, latest_bar_open_time, now)``
on every read (see ``shortlist/read_models.py:22-27`` and
``freshness/evaluator.py:87-111``). We seed
``latest_bar_open_time`` to the newest bar's ``bar_open_time`` (≈16
min old for 15m timeframe, within the 25-min threshold), so the
on-read evaluation returns ``fresh``.

**Risk-trigger neutrality:** to keep ``ranking_score == base_ranking``
(no penalty), the seed avoids all five risk-trigger branches in
``signal_engine/service.py:235-299``:

* ``market_status`` -- ``fresh`` via the freshness_status row above.
* ``context_status`` -- news + sentiment rows for every symbol
  (within 8h / 4h thresholds) AND no connector with
  ``status in {"degraded", "error"}``.
* ``degraded_ai`` -- empty by default (no AI service is degraded
  in the test / live setup).
* ``runtime_state`` -- ``BACKGROUND_MONITORING`` (default).
* ``bar_close_time`` -- newest bar closes 1 min ago, well within
  the 2h expiry threshold.

**Usage (live):**

::

    cd /home/emma/Projects/clay/backend
    python -m scripts.seed_demo_signal_data --symbols SOLUSDT,BTCUSDT
    python -m scripts.seed_demo_signal_data --clean

The first invocation seeds and writes a tracker JSON (default
``scripts/.clay_seed_trackers.json``) with the exact keys to
target on teardown. The second invocation reads the tracker and
deletes only those rows (no TRUNCATE).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast


_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_SRC = _BACKEND_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


from sqlalchemy import create_engine, delete  # noqa: E402
from sqlalchemy.engine import CursorResult  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from clay.db.models_context import NewsItem, SentimentSnapshot  # noqa: E402
from clay.db.models_market import MarketBar, MarketFreshnessStatus  # noqa: E402
from clay.db.models_ops import ConnectorStatusHistory  # noqa: E402
from clay.db.repositories_context import ContextRepository  # noqa: E402
from clay.db.repositories_market import MarketRepository  # noqa: E402
from clay.db.repositories_ops import OpsRepository  # noqa: E402


logger = logging.getLogger("clay.scripts.seed_demo_signal_data")


# === Signal-engine-visible constants ===
SOURCE = "binance_spot"
TIMEFRAME = "15m"
TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "1h": 60}
BAR_COUNT = 50
DEFAULT_DB_URL = "postgresql+psycopg://clay:clay@localhost:5432/clay"

# Connector id used to register a healthy source for the seeded symbols.
# Distinctive so ``--clean`` deletes only our row, not other operational
# connectors. The signal pipeline's
# ``OpsRepository.latest_connector_statuses`` dedupes by ``connector_id``
# and reads the most recent row, so a single healthy row is sufficient.
SEED_CONNECTOR_ID = "binance_spot_seed"
SEED_CONNECTOR_TYPE = "market"

NEWS_SOURCE_NAME = "demo_news_seed"
SENTIMENT_SOURCE_NAME = "demo_sentiment_seed"

# Per-symbol base values: ``(close, peak_volume)``. Close matches the
# canonical hermetic test seed in
# ``tests/signal_engine/test_signal_engine_service.py:50``. Peak volume
# is the volume of the newest (most recent) bar; older bars are scaled
# linearly 30%..98% of peak so the newest bar's
# ``rolling_volume_score = bar.volume / max(all volumes) = 1.0``.
#
# Peak volumes are sized ABOVE the live DB's historical max for the
# symbol across all timeframes, so the newest seeded bar owns the
# ``max_volume`` slot in ``build_shortlist_metrics`` and gets
# ``rolling_volume_score = 1.0``. Without this, the seed loses the
# ``max_volume`` race to historical bars and the score drops to ~0.
SYMBOL_PROFILES: dict[str, tuple[float, float]] = {
    "BTCUSDT": (70540.0, 50000.0),
    "ETHUSDT": (3500.0, 200000.0),
    "SOLUSDT": (179.1, 2000000.0),
}


@dataclass
class SeedTrackers:
    """Per-symbol insertion tracking for ``--clean`` teardown.

    Stores the natural keys of every row the ``seed`` call inserted.
    The ``--clean`` path uses these to issue a targeted ``DELETE`` per
    row, never a ``TRUNCATE`` -- so concurrent operational data is
    untouched.
    """

    bar_keys: list[tuple[str, str, str, str]] = field(default_factory=list)
    freshness_keys: list[tuple[str, str, str]] = field(default_factory=list)
    news_keys: list[tuple[str, str, str]] = field(default_factory=list)
    sentiment_keys: list[tuple[str, str, str]] = field(default_factory=list)
    connector_observed_at: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "bar_keys": [list(k) for k in self.bar_keys],
            "freshness_keys": [list(k) for k in self.freshness_keys],
            "news_keys": [list(k) for k in self.news_keys],
            "sentiment_keys": [list(k) for k in self.sentiment_keys],
            "connector_observed_at": self.connector_observed_at,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SeedTrackers:
        return cls(
            bar_keys=[(s, sy, tf, t) for s, sy, tf, t in data["bar_keys"]],
            freshness_keys=[(s, sy, tf) for s, sy, tf in data["freshness_keys"]],
            news_keys=[(s, h, t) for s, h, t in data["news_keys"]],
            sentiment_keys=[(s, sy, t) for s, sy, t in data["sentiment_keys"]],
            connector_observed_at=cast(str | None, data.get("connector_observed_at")),
        )


def _build_bars(symbol: str, close: float, peak_volume: float, now: datetime) -> list[dict[str, object]]:
    """Build 50 bars for ``symbol``; newest has the peak volume.

    The volume ramps linearly 30% -> 100% of ``peak_volume`` from the
    oldest bar to the newest, so the newest bar (which is the one
    ``_pick_preferred_bars`` selects for the signal) has
    ``rolling_volume_score = 1.0`` and the base ranking is
    ``0.55 * 1.0 + 0.45 * 0.25 = 0.66`` (constant 2.5% spread between
    high/low gives ``rolling_volatility_score = 0.25`` for every bar).
    """
    tf_minutes = TIMEFRAME_MINUTES[TIMEFRAME]
    bars: list[dict[str, object]] = []
    for i in range(BAR_COUNT):
        bars_from_newest = BAR_COUNT - 1 - i
        bar_open_time = now - timedelta(minutes=1 + tf_minutes * (bars_from_newest + 1))
        bar_close_time = now - timedelta(minutes=tf_minutes * bars_from_newest)
        vol_ratio = 0.3 + 0.7 * (i / (BAR_COUNT - 1))
        volume = peak_volume * vol_ratio
        bars.append(
            {
                "symbol": symbol,
                "timeframe": TIMEFRAME,
                "open": close * 0.99,
                "high": close * 1.01,
                "low": close * 0.985,
                "close": close,
                "volume": volume,
                "quote_volume": close * volume,
                "source": SOURCE,
                "bar_open_time": bar_open_time,
                "bar_close_time": bar_close_time,
            }
        )
    return bars


def _news_payload(symbol: str, now: datetime) -> dict[str, object]:
    return {
        "source_name": NEWS_SOURCE_NAME,
        "headline": f"[seed] {symbol} pipeline-validation row",
        "summary": "Synthetic news row from the seed harness; not a real-world headline.",
        "published_at": now - timedelta(minutes=15),
        "symbol": symbol,
        "source_url": f"https://example.invalid/seed/{symbol.lower()}",
    }


def _sentiment_payload(symbol: str, now: datetime) -> dict[str, object]:
    return {
        "source_name": SENTIMENT_SOURCE_NAME,
        "symbol": symbol,
        "sentiment_label": "bullish",
        "sentiment_score": 0.78,
        "captured_at": now - timedelta(minutes=10),
    }


def seed(session: Session, symbols: list[str]) -> SeedTrackers:
    """Insert the demo data. Returns the per-row trackers for ``--clean``."""
    now = datetime.now(UTC)
    market_repo = MarketRepository(session)
    context_repo = ContextRepository(session)
    ops_repo = OpsRepository(session)
    trackers = SeedTrackers()

    for symbol in symbols:
        if symbol not in SYMBOL_PROFILES:
            raise ValueError(
                f"unknown symbol {symbol!r}; supported: {list(SYMBOL_PROFILES)}"
            )
        close, peak_volume = SYMBOL_PROFILES[symbol]

        bars = _build_bars(symbol, close, peak_volume, now)
        market_repo.upsert_market_bars(bars)
        trackers.bar_keys.extend(
            (b["source"], b["symbol"], b["timeframe"], b["bar_open_time"].isoformat())  # type: ignore[misc]
            for b in bars
        )

        market_repo.upsert_freshness_status(
            source=SOURCE,
            symbol=symbol,
            timeframe=TIMEFRAME,
            freshness_state="fresh",
            evaluated_at=now,
            latest_bar_open_time=cast(datetime, bars[-1]["bar_open_time"]),
            is_stale=False,
        )
        trackers.freshness_keys.append((SOURCE, symbol, TIMEFRAME))

    for symbol in symbols:
        news = _news_payload(symbol, now)
        context_repo.store_news_items([news])
        trackers.news_keys.append(
            (news["source_name"], news["headline"], news["published_at"].isoformat())  # type: ignore[misc]
        )

        sent = _sentiment_payload(symbol, now)
        context_repo.store_sentiment_snapshots([sent])
        trackers.sentiment_keys.append(
            (sent["source_name"], sent["symbol"], sent["captured_at"].isoformat())  # type: ignore[misc]
        )

    ops_repo.record_connector_status(
        connector_id=SEED_CONNECTOR_ID,
        connector_type=SEED_CONNECTOR_TYPE,
        status="healthy",
        observed_at=now,
    )
    trackers.connector_observed_at = now.isoformat()

    session.commit()
    return trackers


def clean(session: Session, trackers: SeedTrackers) -> int:
    """Delete exactly the rows the ``seed`` call inserted.

    Returns the number of rows deleted. Uses per-row ``DELETE`` keyed
    on the natural key stored in the tracker -- never ``TRUNCATE``.
    """
    removed = 0

    for source, symbol, tf, bar_open_time_iso in trackers.bar_keys:
        bar_open_time = datetime.fromisoformat(bar_open_time_iso)
        res = session.execute(
            delete(MarketBar).where(
                MarketBar.source == source,
                MarketBar.symbol == symbol,
                MarketBar.timeframe == tf,
                MarketBar.bar_open_time == bar_open_time,
            )
        )
        removed += cast(CursorResult, res).rowcount or 0

    for source, symbol, tf in trackers.freshness_keys:
        res = session.execute(
            delete(MarketFreshnessStatus).where(
                MarketFreshnessStatus.source == source,
                MarketFreshnessStatus.symbol == symbol,
                MarketFreshnessStatus.timeframe == tf,
            )
        )
        removed += cast(CursorResult, res).rowcount or 0

    for source_name, headline, published_at_iso in trackers.news_keys:
        published_at = datetime.fromisoformat(published_at_iso)
        res = session.execute(
            delete(NewsItem).where(
                NewsItem.source_name == source_name,
                NewsItem.headline == headline,
                NewsItem.published_at == published_at,
            )
        )
        removed += cast(CursorResult, res).rowcount or 0

    for source_name, symbol, captured_at_iso in trackers.sentiment_keys:
        captured_at = datetime.fromisoformat(captured_at_iso)
        res = session.execute(
            delete(SentimentSnapshot).where(
                SentimentSnapshot.source_name == source_name,
                SentimentSnapshot.symbol == symbol,
                SentimentSnapshot.captured_at == captured_at,
            )
        )
        removed += cast(CursorResult, res).rowcount or 0

    if trackers.connector_observed_at is not None:
        observed_at = datetime.fromisoformat(trackers.connector_observed_at)
        res = session.execute(
            delete(ConnectorStatusHistory).where(
                ConnectorStatusHistory.connector_id == SEED_CONNECTOR_ID,
                ConnectorStatusHistory.observed_at == observed_at,
            )
        )
        removed += cast(CursorResult, res).rowcount or 0

    session.commit()
    return removed


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Seed the demo signal pipeline (market bars, freshness, news, sentiment, "
            "connector status) so FSM session start has an eligible ranked signal. "
            "Use --clean to remove exactly the rows the previous seed inserted."
        ),
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help=(
            "Comma-separated symbols to seed (e.g. SOLUSDT,BTCUSDT). "
            "Omit when --clean is set."
        ),
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Tear down the previously-seeded rows (reads the tracker file).",
    )
    parser.add_argument(
        "--tracker-file",
        type=str,
        default=str(_BACKEND_ROOT / "scripts" / ".clay_seed_trackers.json"),
        help="Path to the tracker JSON (written on seed, read on --clean).",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("CLAY_DATABASE_URL", DEFAULT_DB_URL),
        help="SQLAlchemy DB URL (default: $CLAY_DATABASE_URL or local clay).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    engine = create_engine(args.database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)

    if args.clean:
        tracker_path = Path(args.tracker_file)
        if not tracker_path.exists():
            print(
                f"ERROR: --clean requires tracker file at {tracker_path}; not found.",
                file=sys.stderr,
            )
            return 2
        trackers = SeedTrackers.from_json(json.loads(tracker_path.read_text()))
        with SessionLocal() as session:
            removed = clean(session, trackers)
        print(f"Cleaned {removed} rows.")
        tracker_path.unlink(missing_ok=True)
        return 0

    if not args.symbols:
        print(
            "ERROR: --symbols is required for seed (e.g. --symbols SOLUSDT,BTCUSDT).",
            file=sys.stderr,
        )
        return 2

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    with SessionLocal() as session:
        trackers = seed(session, symbols)

    tracker_path = Path(args.tracker_file)
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(json.dumps(trackers.to_json(), indent=2))

    print(
        f"Seeded for {symbols}: "
        f"{len(trackers.bar_keys)} bars, "
        f"{len(trackers.freshness_keys)} freshness, "
        f"{len(trackers.news_keys)} news, "
        f"{len(trackers.sentiment_keys)} sentiment, "
        f"1 connector status. "
        f"Trackers: {tracker_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
