from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Identity, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from clay.db.base import Base


class MarketBar(Base):
    __tablename__ = "market_bars"
    __table_args__ = (
        UniqueConstraint("source", "symbol", "timeframe", "bar_open_time", name="uq_market_bar"),
        Index("market_bars_bar_open_time_idx", text("bar_open_time DESC")),
        {"schema": "market"},
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    quote_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    bar_open_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    bar_close_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OrderBookSummary(Base):
    __tablename__ = "orderbook_summaries"
    __table_args__ = (
        Index("orderbook_summaries_captured_at_idx", text("captured_at DESC")),
        {"schema": "market"},
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    best_bid: Mapped[float] = mapped_column(Float)
    best_ask: Mapped[float] = mapped_column(Float)
    bid_depth_top: Mapped[float | None] = mapped_column(Float, nullable=True)
    ask_depth_top: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    source: Mapped[str] = mapped_column(String(32))


class MarketFreshnessStatus(Base):
    __tablename__ = "market_freshness_status"
    __table_args__ = (
        UniqueConstraint("source", "symbol", "timeframe", name="uq_market_freshness_status"),
        {"schema": "market"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    freshness_state: Mapped[str] = mapped_column(String(32), index=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latest_bar_open_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
