from sqlalchemy import select
from sqlalchemy.orm import Session

from clay.db.models_review import SignalFeedback


class ReviewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_feedback(self, payload: dict[str, object]) -> SignalFeedback:
        row = SignalFeedback(**payload)
        self.session.add(row)
        self.session.flush()
        return row

    def list_feedback(
        self,
        *,
        symbol: str | None = None,
        strategy_mode: str | None = None,
        model_version: str | None = None,
        confidence_band: str | None = None,
        limit: int = 50,
    ) -> list[SignalFeedback]:
        query = select(SignalFeedback).order_by(SignalFeedback.created_at.desc())
        if symbol:
            query = query.where(SignalFeedback.symbol == symbol)
        if strategy_mode:
            query = query.where(SignalFeedback.strategy_mode == strategy_mode)
        if model_version:
            query = query.where(SignalFeedback.model_version == model_version)
        if confidence_band:
            query = query.where(SignalFeedback.confidence_band == confidence_band)
        query = query.limit(limit)
        return list(self.session.scalars(query).all())
