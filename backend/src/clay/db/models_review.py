from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from clay.db.base import Base


class SignalFeedback(Base):
    __tablename__ = "signal_feedback"
    __table_args__ = {"schema": "review"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    signal_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    strategy_mode: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    model_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    confidence_band: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    outcome_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    feedback_label: Mapped[str] = mapped_column(String(32), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
