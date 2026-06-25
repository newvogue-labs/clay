from __future__ import annotations


from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clay.audit.writer import AuditWriter
from clay.core.clock import Clock, SystemClock
from clay.db.models_demo import DemoTradeRecord
from clay.db.repositories_demo import DemoRepository
from clay.demo_trading.models import (
    DemoActiveSessionSnapshot,
    DemoReadinessGateSnapshot,
    DemoReadinessSnapshot,
    DemoTradeLogCommand,
    DemoTradeRecordSnapshot,
    DemoTradingSnapshot,
    OutcomeStatus,
)
from clay.events.bus import EventBus
from clay.session_control.service import SessionControlService
from clay.workspace.service import WorkspaceService


OUTCOME_STATUSES: tuple[OutcomeStatus, ...] = (
    "matched",
    "missed",
    "late_matched",
    "mismatched",
    "unresolved",
)


class DemoTradingService:
    def __init__(
        self,
        *,
        session_control_service: SessionControlService,
        workspace_service: WorkspaceService,
        audit_writer: AuditWriter,
        event_bus: EventBus,
        clock: Clock = SystemClock(),
    ) -> None:
        self.session_control_service = session_control_service
        self.workspace_service = workspace_service
        self.audit_writer = audit_writer
        self.event_bus = event_bus
        self._clock = clock

    def build_snapshot(self, session: Session) -> DemoTradingSnapshot:
        repository = DemoRepository(session)
        records = repository.list_trade_records(limit=20)
        all_records = repository.list_all_trade_records()
        return DemoTradingSnapshot(
            readiness=self._build_readiness(all_records),
            active_session=self._build_active_session(session),
            records=[self._serialize_record(record) for record in records],
        )

    def log_current_trade(
        self,
        session: Session,
        command: DemoTradeLogCommand,
    ) -> DemoTradingSnapshot:
        active_session = self._require_active_session(session)
        assert active_session.session_id is not None
        session_id = active_session.session_id

        repository = DemoRepository(session)
        open_record = repository.get_open_record_for_session(session_id)
        if open_record is not None:
            raise ValueError(
                f"Session {session_id} already has an open record "
                f"(id={open_record.id}). Complete or ingest it before logging a new trade."
            )

        now = self._clock.now()
        initial_outcome = "missed" if command.operator_action == "skipped" else "unresolved"
        initial_status = "not_entered" if command.operator_action == "skipped" else "awaiting_result"

        try:
            record = repository.create_trade_record(
                {
                    "session_id": session_id,
                    "signal_id": active_session.current_signal_id,
                    "symbol": active_session.current_pair_symbol,
                    "executed_symbol": command.executed_symbol,
                    "operator_action": command.operator_action,
                    "operator_notes": command.operator_notes,
                    "recorded_at": now,
                    "broker_status": initial_status,
                    "outcome_status": initial_outcome,
                }
            )
            session.commit()
        except IntegrityError as e:
            raise ValueError(
                f"Session {session_id} already has an open record (race detected). "
                "Duplicate prevented by database constraint."
            ) from e

        self._write_and_publish(
            "demo.trade.logged",
            {
                "record_id": record.id,
                "session_id": record.session_id,
                "signal_id": record.signal_id,
                "symbol": record.symbol,
                "executed_symbol": record.executed_symbol,
                "operator_action": record.operator_action,
                "outcome_status": record.outcome_status,
            },
        )
        return self.build_snapshot(session)

    def ingest_result(
        self,
        session: Session,
        *,
        record_id: int,
        external_trade_id: str | None,
        broker_status: str,
        entry_price: float | None,
        exit_price: float | None,
        pnl_pct: float,
    ) -> DemoTradingSnapshot:
        repository = DemoRepository(session)
        record = repository.get_trade_record(record_id)
        if record is None:
            raise ValueError("demo trade record not found")
        if record.operator_action == "skipped":
            raise ValueError("skipped records do not accept observed trade results")

        outcome_status = self._classify_outcome(record)
        observed_at = self._clock.now()
        repository.update_trade_record(
            record_id,
            external_trade_id=external_trade_id,
            broker_status=broker_status,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl_pct=pnl_pct,
            observed_at=observed_at,
            outcome_status=outcome_status,
        )
        session.commit()
        self._write_and_publish(
            "demo.result.ingested",
            {
                "record_id": record_id,
                "session_id": record.session_id,
                "signal_id": record.signal_id,
                "symbol": record.symbol,
                "outcome_status": outcome_status,
                "pnl_pct": pnl_pct,
            },
        )
        return self.build_snapshot(session)

    def _require_active_session(self, session: Session) -> DemoActiveSessionSnapshot:
        active_session = self._build_active_session(session)
        if not active_session.can_log_decision:
            raise ValueError(active_session.blocking_reason or "demo logging is blocked")
        if (
            active_session.session_id is None
            or active_session.current_pair_symbol is None
            or active_session.current_signal_id is None
        ):
            raise ValueError("active session has no focused signal")
        return active_session

    def _build_active_session(self, session: Session) -> DemoActiveSessionSnapshot:
        session_snapshot = self.session_control_service.build_snapshot(session)
        workspace_snapshot = self.workspace_service.build_snapshot(session)
        lifecycle = session_snapshot.lifecycle

        blocking_reason: str | None = None
        can_log_decision = False
        if lifecycle.lifecycle_state != "active_session":
            blocking_reason = "Start an active session before logging demo trades."
        elif not workspace_snapshot.workspace_state.can_log_decision:
            blocking_reason = (
                workspace_snapshot.workspace_state.blocking_reason
                or "Focused signal is not actionable for demo logging."
            )
        else:
            can_log_decision = True

        return DemoActiveSessionSnapshot(
            lifecycle_state=lifecycle.lifecycle_state,
            session_id=lifecycle.session_id,
            current_pair_symbol=lifecycle.current_pair_symbol,
            current_signal_id=lifecycle.current_signal_id,
            can_log_decision=can_log_decision,
            blocking_reason=blocking_reason,
        )

    def _build_readiness(self, records: list[DemoTradeRecord]) -> DemoReadinessSnapshot:
        counts = {status: 0 for status in OUTCOME_STATUSES}
        distinct_sessions = {record.session_id for record in records}
        cumulative_pnl_pct = 0.0
        profitable_record_count = 0

        for record in records:
            counts[record.outcome_status] = counts.get(record.outcome_status, 0) + 1
            if record.pnl_pct is not None:
                cumulative_pnl_pct += record.pnl_pct
                if record.pnl_pct > 0:
                    profitable_record_count += 1

        cumulative_pnl_pct = round(cumulative_pnl_pct, 2)
        total_records = len(records)
        resolved_record_count = total_records - counts["unresolved"]
        losing_record_count = sum(
            1
            for record in records
            if record.pnl_pct is not None and record.pnl_pct < 0
        )

        gates = [
            DemoReadinessGateSnapshot(
                gate_id="session-count",
                label="Session count",
                status="pass" if len(distinct_sessions) >= 5 else "warn",
                detail=f"{len(distinct_sessions)} / 5 demo sessions recorded.",
            ),
            DemoReadinessGateSnapshot(
                gate_id="result-resolution",
                label="Result resolution",
                status="pass" if counts["unresolved"] == 0 else "fail",
                detail=f"{resolved_record_count} resolved, {counts['unresolved']} unresolved records.",
            ),
            DemoReadinessGateSnapshot(
                gate_id="signal-alignment",
                label="Signal alignment",
                status="pass" if counts["mismatched"] == 0 else "fail",
                detail=f"{counts['mismatched']} mismatched demo outcomes recorded.",
            ),
            DemoReadinessGateSnapshot(
                gate_id="pnl-discipline",
                label="PnL discipline",
                status=(
                    "pass"
                    if cumulative_pnl_pct > 0 and profitable_record_count >= losing_record_count
                    else "warn"
                ),
                detail=(
                    f"Cumulative PnL {cumulative_pnl_pct:.2f}% with "
                    f"{profitable_record_count} profitable vs {losing_record_count} losing results."
                ),
            ),
        ]

        if len(distinct_sessions) < 5:
            status = "collecting"
            operator_message = "Keep collecting disciplined demo sessions before the review gate unlocks."
        elif counts["mismatched"] > 0 or counts["unresolved"] > 0 or cumulative_pnl_pct <= 0:
            status = "at_risk"
            operator_message = "Demo stage is not ready yet: resolve mismatches, close open records, or improve PnL."
        else:
            status = "ready_for_review"
            operator_message = "Demo evidence is strong enough to move into formal review."

        return DemoReadinessSnapshot(
            status=status,
            operator_message=operator_message,
            distinct_session_count=len(distinct_sessions),
            total_records=total_records,
            resolved_record_count=resolved_record_count,
            profitable_record_count=profitable_record_count,
            cumulative_pnl_pct=cumulative_pnl_pct,
            outcome_counts=counts,
            gates=gates,
        )

    def _serialize_record(self, record: DemoTradeRecord) -> DemoTradeRecordSnapshot:
        return DemoTradeRecordSnapshot(
            record_id=record.id,
            session_id=record.session_id,
            signal_id=record.signal_id,
            symbol=record.symbol,
            executed_symbol=record.executed_symbol,
            operator_action=record.operator_action,
            operator_notes=record.operator_notes,
            recorded_at=record.recorded_at.isoformat(),
            external_trade_id=record.external_trade_id,
            broker_status=record.broker_status,
            entry_price=record.entry_price,
            exit_price=record.exit_price,
            pnl_pct=record.pnl_pct,
            observed_at=record.observed_at.isoformat() if record.observed_at is not None else None,
            outcome_status=record.outcome_status,
            awaiting_result=record.outcome_status == "unresolved",
            advisory_size_pct=record.advisory_size_pct,
        )

    def _classify_outcome(self, record: DemoTradeRecord) -> OutcomeStatus:
        if record.operator_action == "entered":
            return "matched"
        if record.operator_action == "entered_late":
            return "late_matched"
        if record.operator_action == "off_signal":
            return "mismatched"
        if record.operator_action == "skipped":
            return "missed"
        return "unresolved"

    def _write_and_publish(self, event_type: str, payload: dict[str, object]) -> None:
        self.audit_writer.write(event_type, payload)
        self.event_bus.publish("demo.updated", {"event_type": event_type, **payload})
