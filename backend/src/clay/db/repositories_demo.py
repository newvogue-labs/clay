from collections.abc import Collection
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from clay.db.models_demo import DemoTradeRecord

DEFAULT_READ_SCOPE: frozenset[str] = frozenset({"baseline", "live"})


def _validate_scope(source_scope: Collection[str]) -> None:
    if not source_scope:
        raise ValueError(f"source_scope must be non-empty, got {source_scope!r}")


class DemoRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_open_record_for_session(self, session_id: str) -> DemoTradeRecord | None:
        query = (
            select(DemoTradeRecord)
            .where(
                DemoTradeRecord.session_id == session_id,
                DemoTradeRecord.broker_status == "awaiting_result",
            )
            .limit(1)
        )
        return self.session.scalar(query)

    def create_trade_record(self, payload: dict[str, object]) -> DemoTradeRecord:
        record = DemoTradeRecord(**payload)
        self.session.add(record)
        self.session.flush()
        return record

    def get_trade_record(self, record_id: int) -> DemoTradeRecord | None:
        return self.session.get(DemoTradeRecord, record_id)

    def update_trade_record(self, record_id: int, **updates: object) -> DemoTradeRecord:
        record = self.session.get(DemoTradeRecord, record_id)
        if record is None:
            raise ValueError("demo trade record not found")
        for key, value in updates.items():
            setattr(record, key, value)
        self.session.flush()
        return record

    def list_trade_records(
        self, *, limit: int = 50, source_scope: Collection[str] = DEFAULT_READ_SCOPE
    ) -> list[DemoTradeRecord]:
        _validate_scope(source_scope)
        query = (
            select(DemoTradeRecord)
            .where(DemoTradeRecord.source.in_(source_scope))
            .order_by(DemoTradeRecord.recorded_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(query).all())

    def list_all_trade_records(
        self, source_scope: Collection[str] = DEFAULT_READ_SCOPE
    ) -> list[DemoTradeRecord]:
        _validate_scope(source_scope)
        query = (
            select(DemoTradeRecord)
            .where(DemoTradeRecord.source.in_(source_scope))
            .order_by(DemoTradeRecord.recorded_at.desc())
        )
        return list(self.session.scalars(query).all())

    def list_resolved_window(
        self, hours: int, source_scope: Collection[str] = DEFAULT_READ_SCOPE
    ) -> list[DemoTradeRecord]:
        _validate_scope(source_scope)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = (
            select(DemoTradeRecord)
            .where(
                DemoTradeRecord.recorded_at >= cutoff,
                DemoTradeRecord.outcome_status.in_(
                    {"matched", "missed", "late_matched", "mismatched"}
                ),
                DemoTradeRecord.operator_action == "entered",
                DemoTradeRecord.source.in_(source_scope),
            )
            .order_by(DemoTradeRecord.recorded_at.desc())
        )
        return list(self.session.scalars(query).all())

    def list_ordered_recent(
        self, limit: int = 50, source_scope: Collection[str] = DEFAULT_READ_SCOPE
    ) -> list[DemoTradeRecord]:
        _validate_scope(source_scope)
        query = (
            select(DemoTradeRecord)
            .where(
                DemoTradeRecord.operator_action == "entered",
                DemoTradeRecord.source.in_(source_scope),
            )
            .order_by(DemoTradeRecord.recorded_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(query).all())

    def list_open_positions(
        self, source_scope: Collection[str] = DEFAULT_READ_SCOPE
    ) -> list[DemoTradeRecord]:
        _validate_scope(source_scope)
        query = select(DemoTradeRecord).where(
            DemoTradeRecord.broker_status == "awaiting_result",
            DemoTradeRecord.source.in_(source_scope),
        )
        return list(self.session.scalars(query).all())

    def list_session_trades(
        self, session_id: str, source_scope: Collection[str] = DEFAULT_READ_SCOPE
    ) -> list[DemoTradeRecord]:
        _validate_scope(source_scope)
        query = (
            select(DemoTradeRecord)
            .where(
                DemoTradeRecord.session_id == session_id,
                DemoTradeRecord.source.in_(source_scope),
            )
            .order_by(DemoTradeRecord.recorded_at.desc())
        )
        return list(self.session.scalars(query).all())
