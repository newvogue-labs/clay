from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from clay.db.models_market import MarketBar, MarketFreshnessStatus


_source_priority: list[str] | None = None


def set_source_priority(priority: list[str] | None) -> None:
    global _source_priority
    _source_priority = priority


def _priority_index(source: str) -> int:
    if _source_priority is None:
        return 0
    try:
        return _source_priority.index(source)
    except ValueError:
        return len(_source_priority)


class MarketRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_market_bars(
        self,
        bars: list[dict[str, object]],
    ) -> tuple[int, int]:
        """Insert-or-update bars; return ``(inserted, updated)``.

        B5 (MED-C) splits the previous ``int`` return into a
        ``(inserted, updated)`` tuple so the cycle summary can
        report the two counts separately (the
        ``market_records_written`` total is a computed property
        ``= inserted + updated`` in ``IngestionRunSummary`` for
        backward-compat with the pre-B5 ``assert ... == 4`` tests).
        """
        inserted = 0
        updated = 0
        next_sqlite_id = self._next_sqlite_market_bar_id()
        for bar in bars:
            existing = self.session.scalar(
                select(MarketBar).where(
                    MarketBar.source == bar["source"],
                    MarketBar.symbol == bar["symbol"],
                    MarketBar.timeframe == bar["timeframe"],
                    MarketBar.bar_open_time == bar["bar_open_time"],
                ),
            )
            if existing is None:
                payload = dict(bar)
                if payload.get("id") is None and next_sqlite_id is not None:
                    payload["id"] = next_sqlite_id
                    next_sqlite_id += 1
                self.session.add(MarketBar(**payload))
                inserted += 1
                continue

            existing.open = float(bar["open"])
            existing.high = float(bar["high"])
            existing.low = float(bar["low"])
            existing.close = float(bar["close"])
            existing.volume = float(bar["volume"])
            existing.quote_volume = (
                float(bar["quote_volume"]) if bar["quote_volume"] is not None else None
            )
            existing.source = str(bar["source"])
            existing.bar_close_time = bar["bar_close_time"]  # type: ignore[assignment]
            updated += 1

        self.session.flush()
        return inserted, updated

    def _next_sqlite_market_bar_id(self) -> int | None:
        bind = self.session.get_bind()
        if bind is None or bind.dialect.name != "sqlite":
            return None

        current_max = self.session.scalar(select(func.max(MarketBar.id)))
        return int(current_max or 0) + 1

    def upsert_freshness_status(
        self,
        *,
        source: str,
        symbol: str,
        timeframe: str,
        freshness_state: str,
        evaluated_at: datetime,
        latest_bar_open_time: datetime | None,
        is_stale: bool,
    ) -> bool:
        """Upsert a freshness row; return ``True`` iff a state transition occurred.

        B5 Поправка 2 (Emma caught): the previous ``None`` return
        gave the caller no signal of whether the upsert changed
        anything, so ``IngestionRunSummary.freshness_state_transitions``
        could not be computed without re-reading the row. The new
        ``bool`` return is the **transition signal** the
        ``IngestionCycleJob``'s anti-flood diff watches.

        Semantics:

        * INSERT (no existing row) → ``True`` (first observation =
          transition from "unknown").
        * UPDATE with **same** ``freshness_state`` → ``False``
          (timestamp-only touch, no transition).
        * UPDATE with **different** ``freshness_state`` → ``True``
          (real state change).
        """
        existing = self.session.scalar(
            select(MarketFreshnessStatus).where(
                MarketFreshnessStatus.source == source,
                MarketFreshnessStatus.symbol == symbol,
                MarketFreshnessStatus.timeframe == timeframe,
            ),
        )
        if existing is None:
            self.session.add(
                MarketFreshnessStatus(
                    source=source,
                    symbol=symbol,
                    timeframe=timeframe,
                    freshness_state=freshness_state,
                    evaluated_at=evaluated_at,
                    latest_bar_open_time=latest_bar_open_time,
                    is_stale=is_stale,
                ),
            )
            self.session.flush()
            return True

        state_changed = existing.freshness_state != freshness_state
        existing.freshness_state = freshness_state
        existing.evaluated_at = evaluated_at
        existing.latest_bar_open_time = latest_bar_open_time
        existing.is_stale = is_stale
        self.session.flush()
        return state_changed

    def list_latest_bars(
        self,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = 50,
    ) -> list[MarketBar]:
        query: Select[tuple[MarketBar]] = select(MarketBar).order_by(
            MarketBar.bar_close_time.desc(),
        )
        if symbol is not None:
            query = query.where(MarketBar.symbol == symbol)
        if timeframe is not None:
            query = query.where(MarketBar.timeframe == timeframe)

        bars = list(self.session.scalars(query).all())

        if _source_priority is not None:
            bars.sort(key=lambda b: _priority_index(b.source))

        deduped: list[MarketBar] = []
        seen: set[tuple[str, str]] = set()
        for bar in bars:
            key = (bar.symbol, bar.timeframe)
            if key in seen:
                continue
            deduped.append(bar)
            seen.add(key)
            if len(deduped) >= limit:
                break
        return deduped

    def list_freshness_statuses(self) -> list[MarketFreshnessStatus]:
        query = select(MarketFreshnessStatus).order_by(
            MarketFreshnessStatus.symbol.asc(),
            MarketFreshnessStatus.timeframe.asc(),
        )
        rows = list(self.session.scalars(query).all())

        if _source_priority is None:
            return rows  # backward compat: all sources, no collapse

        rows.sort(key=lambda r: _priority_index(r.source))

        deduped: list[MarketFreshnessStatus] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            key = (row.symbol, row.timeframe)
            if key in seen:
                continue
            deduped.append(row)
            seen.add(key)
        return deduped
