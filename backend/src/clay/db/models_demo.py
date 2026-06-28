from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from clay.db.base import Base


class DemoTradeRecord(Base):
    __tablename__ = "demo_trade_records"
    __table_args__ = {"schema": "demo"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    signal_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    executed_symbol: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    operator_action: Mapped[str] = mapped_column(String(32), index=True)
    operator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    external_trade_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    broker_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    outcome_status: Mapped[str] = mapped_column(
        String(32), index=True, default="unresolved"
    )
    advisory_size_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16), server_default=text("'live'"))
