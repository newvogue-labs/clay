from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from clay.db.models_market import MarketBar

from clay.core.clock import VirtualClock
from clay.db.repositories_demo import DemoRepository
from clay.demo_trading.service import DemoTradingService
from clay.replay.models import ReplayRunSummary, ReplayTradeResult
from clay.session_control.service import SessionControlService
from clay.signal_engine.service import SignalEngineService

REPLAY_SCOPE: frozenset[str] = frozenset({"replay"})

FORWARD_BUFFER_BARS = 48
"""Minimum number of forward bars required after entry to resolve a trade.

If fewer bars are available a ``ForwardBufferError`` is raised (fail-closed,
never a silent skip/mismatch).
"""


class ForwardBufferError(ValueError):
    """Raised when there are not enough forward bars to resolve a replay trade."""


def _compute_signal_levels(direction: str, entry_price: float) -> tuple[float, float]:
    """Stop/target prices faithful to ``signal_engine._price_hint`` multipliers.

    Bullish: stop at entry × 0.994 (−0.6 %), target at entry × 1.012 (+1.2 %)
    Bearish: stop at entry × 1.006 (+0.6 %), target at entry × 0.988 (−1.2 %)
    """
    if direction == "bearish":
        return (entry_price * 1.006, entry_price * 0.988)
    return (entry_price * 0.994, entry_price * 1.012)


class RetroResolver:
    """Resolves a replay trade by scanning forward bars for stop/target hits.

    Stop and target prices are provided externally (computed from signal
    metadata by ``_compute_signal_levels``) so that replay faithfully
    reproduces the live ``_price_hint`` multiplier logic.
    """

    @staticmethod
    def resolve(
        entry_bar_index: int,
        bars: Sequence[MarketBar],
        *,
        stop_price: float,
        target_price: float,
        direction: str = "long",
    ) -> ReplayTradeResult:
        if (
            len(bars) <= entry_bar_index
            or len(bars) - entry_bar_index - 1 < FORWARD_BUFFER_BARS
        ):
            raise ForwardBufferError(
                f"Need {FORWARD_BUFFER_BARS} forward bars after entry at index "
                f"{entry_bar_index}, got {len(bars) - entry_bar_index - 1} "
                f"(total_bars={len(bars)})"
            )
        entry = bars[entry_bar_index]
        entry_price = entry.close
        # pylint: disable=possibly-used-before-assignment
        for bar in bars[entry_bar_index + 1 :]:
            if direction == "long":
                if bar.low <= stop_price:
                    return ReplayTradeResult(
                        session_id="",
                        signal_id="",
                        symbol=entry.symbol,
                        direction=direction,
                        entry_bar_time=entry.bar_close_time,
                        entry_price=entry_price,
                        exit_price=stop_price,
                        exit_bar_time=bar.bar_close_time,
                        pnl_pct=round((stop_price / entry_price - 1) * 100, 2),
                        outcome_status="matched",
                        reason="stop_hit",
                    )
                if bar.high >= target_price:
                    return ReplayTradeResult(
                        session_id="",
                        signal_id="",
                        symbol=entry.symbol,
                        direction=direction,
                        entry_bar_time=entry.bar_close_time,
                        entry_price=entry_price,
                        exit_price=target_price,
                        exit_bar_time=bar.bar_close_time,
                        pnl_pct=round((target_price / entry_price - 1) * 100, 2),
                        outcome_status="matched",
                        reason="target_hit",
                    )
            else:  # short
                if bar.high >= stop_price:
                    return ReplayTradeResult(
                        session_id="",
                        signal_id="",
                        symbol=entry.symbol,
                        direction=direction,
                        entry_bar_time=entry.bar_close_time,
                        entry_price=entry_price,
                        exit_price=stop_price,
                        exit_bar_time=bar.bar_close_time,
                        pnl_pct=round((1 - stop_price / entry_price) * 100, 2),
                        outcome_status="matched",
                        reason="stop_hit",
                    )
                if bar.low <= target_price:
                    return ReplayTradeResult(
                        session_id="",
                        signal_id="",
                        symbol=entry.symbol,
                        direction=direction,
                        entry_bar_time=entry.bar_close_time,
                        entry_price=entry_price,
                        exit_price=target_price,
                        exit_bar_time=bar.bar_close_time,
                        pnl_pct=round((1 - target_price / entry_price) * 100, 2),
                        outcome_status="matched",
                        reason="target_hit",
                    )

        raise ForwardBufferError(
            f"Trade for {entry.symbol} at {entry.bar_close_time.isoformat()} "
            f"did not hit stop ({stop_price:.4f}) or target ({target_price:.4f}) "
            f"within {FORWARD_BUFFER_BARS} forward bars"
        )


@dataclass
class _OpenTrade:
    entry_bar_index: int
    record_id: int
    session_id: str
    signal_id: str
    symbol: str
    direction: str
    entry_price: float
    entry_bar_time: datetime
    stop_price: float
    target_price: float


class ReplayHarness:
    """Runs replay sessions through the real service layer.

    At each time step the harness:

    1. Advances ``VirtualClock`` to ``bar.bar_close_time``.
    2. If no open trade, calls ``build_snapshot(source_scope={replay})``.
    3. If an actionable signal exists, calls ``start_session(source_scope={replay})``
       and logs a demo trade with ``source='replay'`` (via the repository directly).
    4. If an open trade exists, invokes ``RetroResolver`` on forward bars.
    5. When resolved: calls ``ingest_result`` → ``complete_session`` →
       ``close_review``.

    All DB reads are scoped to ``source_scope={replay}``.
    All DB writes carry ``source='replay'``.
    Determinism: same bars + same clock → same trades.
    """

    def __init__(
        self,
        session: Session,
        clock: VirtualClock,
        session_control: SessionControlService,
        signal_engine: SignalEngineService,
        demo_trading: DemoTradingService,
    ) -> None:
        self._session = session
        self._clock = clock
        self._session_control = session_control
        self._signal_engine = signal_engine
        self._demo_trading = demo_trading
        self._open: _OpenTrade | None = None

    # ── Main entry point ────────────────────────────────────────────────────

    def run(self, symbol: str, timeframe: str) -> ReplayRunSummary:
        query = (
            select(MarketBar)
            .where(MarketBar.symbol == symbol, MarketBar.timeframe == timeframe)
            .order_by(MarketBar.bar_close_time.asc())
        )
        bars = list(self._session.scalars(query).all())
        summary = ReplayRunSummary()

        for idx, bar in enumerate(bars):
            bar_time = bar.bar_close_time
            if bar_time.tzinfo is None:
                bar_time = bar_time.replace(tzinfo=UTC)
            self._clock.set(bar_time)
            summary.bars_processed += 1

            if self._open is not None:
                self._try_resolve(idx, bars, summary)
                continue

            signal_snapshot = self._signal_engine.build_snapshot(
                self._session,
                source_scope=REPLAY_SCOPE,
            )
            top = next(
                (
                    s
                    for s in signal_snapshot.signals
                    if s.state in {"active", "weakening"}
                ),
                None,
            )
            if top is None:
                continue

            try:
                self._session_control.start_session(
                    self._session,
                    source_scope=REPLAY_SCOPE,
                )
            except ValueError:
                continue

            summary.sessions_started += 1
            trade = self._log_trade(top)
            stop_price, target_price = _compute_signal_levels(top.direction, bar.close)
            self._open = _OpenTrade(
                entry_bar_index=idx,
                record_id=trade.id,
                session_id=trade.session_id,
                signal_id=top.signal_id,
                symbol=top.symbol,
                direction=top.direction,
                entry_price=bar.close,
                entry_bar_time=bar.bar_close_time,
                stop_price=stop_price,
                target_price=target_price,
            )

        return summary

    # ── Internals ────────────────────────────────────────────────────────────

    def _log_trade(self, signal) -> object:
        active = self._demo_trading._require_active_session(self._session)
        repo = DemoRepository(self._session)
        now = self._clock.now()
        record = repo.create_trade_record(
            {
                "session_id": active.session_id,
                "signal_id": active.current_signal_id,
                "symbol": active.current_pair_symbol,
                "executed_symbol": signal.symbol,
                "operator_action": "entered",
                "recorded_at": now,
                "broker_status": "awaiting_result",
                "outcome_status": "unresolved",
                "advisory_size_pct": 2.0,
                "source": "replay",
            }
        )
        self._session.commit()
        return record

    def _try_resolve(self, idx: int, bars: list, summary: ReplayRunSummary) -> None:
        if self._open is None:
            return
        try:
            result = RetroResolver.resolve(
                self._open.entry_bar_index,
                bars,
                stop_price=self._open.stop_price,
                target_price=self._open.target_price,
                direction=self._open.direction,
            )
        except ForwardBufferError:
            return

        result.session_id = self._open.session_id
        result.signal_id = self._open.signal_id

        self._demo_trading.ingest_result(
            self._session,
            record_id=self._open.record_id,
            external_trade_id=None,
            broker_status="closed",
            entry_price=self._open.entry_price,
            exit_price=result.exit_price,
            pnl_pct=result.pnl_pct,
        )

        self._session_control.complete_session(self._session)
        self._session_control.close_review(self._session)

        summary.trades.append(result)
        summary.trades_resolved += 1
        self._open = None
