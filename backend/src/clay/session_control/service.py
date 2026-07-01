from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.core.clock import Clock, SystemClock
from clay.db.repositories_runtime_state import SessionStateRepository
from clay.events.bus import EventBus
from clay.runtime.manager import RuntimeManager
from clay.runtime.states import RuntimeState
from clay.session_control.models import (
    PairReplacementReviewSnapshot,
    SessionBriefingSignal,
    SessionBriefingSnapshot,
    SessionControlSnapshot,
    SessionLifecycleSnapshot,
    SessionPreflightCheck,
    SessionPreflightSnapshot,
)
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService


@dataclass
class ActiveSessionRecord:
    session_id: str
    current_pair_symbol: str
    current_signal_id: str | None
    strategy_mode: str
    started_at: datetime
    paused_at: datetime | None = None


@dataclass
class PendingReplacementReview:
    review_id: str
    current_symbol: str
    proposed_symbol: str
    created_at: datetime


class SessionControlService:
    def __init__(
        self,
        *,
        runtime_manager: RuntimeManager,
        signal_engine_service: SignalEngineService,
        ai_control_service: AIControlService,
        workspace_service: WorkspaceService,
        audit_writer: AuditWriter,
        event_bus: EventBus,
        config_loader: ConfigLoader,
        session_factory: sessionmaker | None = None,
        clock: Clock = SystemClock(),
    ) -> None:
        self.runtime_manager = runtime_manager
        self.signal_engine_service = signal_engine_service
        self.ai_control_service = ai_control_service
        self.workspace_service = workspace_service
        self.audit_writer = audit_writer
        self.event_bus = event_bus
        self.config_loader = config_loader
        self.session_factory = session_factory
        self._clock = clock
        # ``_active_session`` and ``_pending_replacement`` are restored from the
        # ``ops.session_state`` singleton row when a ``session_factory`` is
        # supplied. Without one (legacy callers and pre-A4 tests), the service
        # falls back to the in-memory defaults and stays non-persistent.
        if session_factory is None:
            self._active_session: ActiveSessionRecord | None = None
            self._pending_replacement: PendingReplacementReview | None = None
        else:
            with session_factory() as session:
                self._restore_from_db(session)
                session.commit()

    def _restore_from_db(self, session: Session) -> None:
        """Hydrate ``_active_session`` and ``_pending_replacement`` from the
        ``session_state`` singleton row.

        Discriminator for active session: ``session_id``. If ``None``, there
        is no active session. If set, the other required fields
        (``started_at``, ``strategy_mode``, ``current_pair_symbol``) must be
        populated too — otherwise the row is inconsistent (corrupted by
        manual psql or a future bug) and we fail-fast with ``ValueError``.
        ``current_signal_id`` and ``paused_at`` are legitimately nullable.

        Discriminator for pending replacement: ``pending_replacement_id``.
        Same rules for the other pending_* fields.
        """
        state = SessionStateRepository(session).get_or_create()

        if state.session_id is None:
            self._active_session: ActiveSessionRecord | None = None
        else:
            if state.started_at is None:
                raise ValueError(
                    "session_state row inconsistent: session_id set but started_at is NULL"
                )
            if state.strategy_mode is None:
                raise ValueError(
                    "session_state row inconsistent: session_id set but strategy_mode is NULL"
                )
            if state.current_pair_symbol is None:
                raise ValueError(
                    "session_state row inconsistent: session_id set but current_pair_symbol is NULL"
                )
            self._active_session = ActiveSessionRecord(
                session_id=state.session_id,
                current_pair_symbol=state.current_pair_symbol,
                current_signal_id=state.current_signal_id,
                strategy_mode=state.strategy_mode,
                started_at=state.started_at,
                paused_at=state.paused_at,
            )

        if state.pending_replacement_id is None:
            self._pending_replacement: PendingReplacementReview | None = None
        else:
            if state.pending_current_symbol is None:
                raise ValueError(
                    "session_state row inconsistent: pending_replacement_id set but "
                    "pending_current_symbol is NULL"
                )
            if state.pending_proposed_symbol is None:
                raise ValueError(
                    "session_state row inconsistent: pending_replacement_id set but "
                    "pending_proposed_symbol is NULL"
                )
            if state.pending_created_at is None:
                # Same fail-fast contract as the other pending_* fields: the
                # discriminator ``pending_replacement_id`` is set, so all
                # sibling fields must be populated too. A NULL here means a
                # corrupted row (manual psql or a future bug) and silently
                # substituting ``datetime.now(UTC)`` would lose the original
                # pending-review timestamp. (A4 follow-up #2.)
                raise ValueError(
                    "session_state row inconsistent: pending_replacement_id set but "
                    "pending_created_at is NULL"
                )
            self._pending_replacement = PendingReplacementReview(
                review_id=state.pending_replacement_id,
                current_symbol=state.pending_current_symbol,
                proposed_symbol=state.pending_proposed_symbol,
                created_at=state.pending_created_at,
            )

    def _persist_session_state(self, session: Session) -> None:
        """Write a full snapshot of ``_active_session`` and
        ``_pending_replacement`` to the ``session_state`` singleton row.

        All 10 fields are written on every call (full snapshot, not partial
        update) so the DB always mirrors the in-memory state. Singleton
        table → 1 UPDATE per mutation. Idempotent: replaying the same
        in-memory state produces the same row.
        """
        active = self._active_session
        pending = self._pending_replacement
        SessionStateRepository(session).save(
            session_id=active.session_id if active else None,
            current_pair_symbol=active.current_pair_symbol if active else None,
            current_signal_id=active.current_signal_id if active else None,
            strategy_mode=active.strategy_mode if active else None,
            started_at=active.started_at if active else None,
            paused_at=active.paused_at if active else None,
            pending_replacement_id=pending.review_id if pending else None,
            pending_current_symbol=pending.current_symbol if pending else None,
            pending_proposed_symbol=pending.proposed_symbol if pending else None,
            pending_created_at=pending.created_at if pending else None,
        )

    def reconcile_runtime_state(self) -> None:
        """Reconcile ``runtime_manager`` with the restored ``_active_session``.

        Closes A4 §6 Q2 (and the analogous issue raised in A6 recon):
        after a restart, ``runtime_manager`` defaults to
        ``BACKGROUND_MONITORING``. If ``_active_session`` was restored
        from ``session_state`` on init, the
        ``_build_lifecycle`` switch falls through to the final
        ``else: lifecycle_state = "review"`` branch — a false-positive,
        since the session was actually ``ACTIVE_SESSION`` or ``PAUSED``
        before the crash. This method projects the restored session
        back onto the FSM via ``RuntimeManager.reconcile_to`` (see
        ``manager.py`` for the contract: boot-safety by design,
        whitelist-guarded, no path/readiness validation).

        Rule (input → output):

        - ``_active_session is None`` (no session restored) →
          no-op; ``runtime_manager`` stays at its default
          ``BACKGROUND_MONITORING``.
        - ``_active_session.paused_at is not None`` (was paused) →
          ``reconcile_to(PAUSED)``.
        - otherwise (``_active_session.paused_at is None``,
          was active) → ``reconcile_to(ACTIVE_SESSION)``.

        No-op if ``_active_session is None`` (nothing to reconcile).

        The ``reconcile_to`` whitelist guarantees we never project
        onto ``BACKGROUND_MONITORING`` / ``REVIEW`` / ``DEGRADED`` —
        those are operator-action targets, not restore targets.

        Called from ``bootstrap.build_services`` (and from the
        integration-suite factory) **after** ``__init__`` finishes
        restore, **before** any ``build_snapshot`` is called by
        request handlers. Order is load-bearing: without it,
        ``_build_lifecycle`` would return the false-positive
        ``"review"`` for the first snapshot after a restart.
        """
        if self._active_session is None:
            return
        if self._active_session.paused_at is not None:
            self.runtime_manager.reconcile_to(RuntimeState.PAUSED)
        else:
            self.runtime_manager.reconcile_to(RuntimeState.ACTIVE_SESSION)

    def build_snapshot(
        self,
        session: Session,
        *,
        for_start: bool = False,
        source_scope: Collection[str] | None = None,
    ) -> SessionControlSnapshot:
        signal_snapshot = self.signal_engine_service.build_snapshot(
            session, source_scope=source_scope
        )
        ai_snapshot = self.ai_control_service.build_snapshot(session)
        preflight = self._build_preflight(
            session,
            signal_snapshot,
            ai_snapshot,
            for_start=for_start,
            source_scope=source_scope,
        )
        briefing = self._build_briefing(signal_snapshot, ai_snapshot)
        lifecycle = self._build_lifecycle(preflight)
        pending_replacement = self._build_pending_replacement(signal_snapshot)
        return SessionControlSnapshot(
            preflight=preflight,
            briefing=briefing,
            lifecycle=lifecycle,
            pending_pair_replacement=pending_replacement,
        )

    def start_session(
        self, session: Session, source_scope: Collection[str] | None = None
    ) -> SessionControlSnapshot:
        snapshot = self.build_snapshot(
            session, for_start=True, source_scope=source_scope
        )
        if snapshot.preflight.status != "pass":
            raise ValueError(snapshot.preflight.blocking_reason or "preflight blocked")

        top_signal = next(
            (
                signal
                for signal in snapshot.briefing.shortlist
                if signal.state in {"active", "weakening"}
            ),
            None,
        )
        if top_signal is None:
            raise ValueError("no eligible signal to start session")

        if self.runtime_manager.snapshot().state == RuntimeState.BACKGROUND_MONITORING:
            self.runtime_manager.transition_to(RuntimeState.PRE_SESSION)
        if self.runtime_manager.snapshot().state == RuntimeState.PRE_SESSION:
            self.runtime_manager.transition_to(RuntimeState.ACTIVE_SESSION)

        self.workspace_service.set_focus(
            symbol=top_signal.symbol,
            focus_source="session_start",
            signal_id=top_signal.signal_id,
            session=session,
        )
        # Capture payload locals before mutating in-memory; the event is
        # published last so a failed persist leaves no half-state behind.
        new_session_id = str(uuid4())
        new_started_at = self._clock.now()
        self._active_session = ActiveSessionRecord(
            session_id=new_session_id,
            current_pair_symbol=top_signal.symbol,
            current_signal_id=top_signal.signal_id,
            strategy_mode=snapshot.briefing.active_strategy,
            started_at=new_started_at,
        )
        self._pending_replacement = None
        # write-through: persist the new active session before publishing the
        # event. If the DB write raises, in-memory state stays consistent
        # with the previous commit and the caller can safely retry.
        self._persist_session_state(session)
        self._write_and_publish(
            "session.started",
            {
                "session_id": new_session_id,
                "symbol": top_signal.symbol,
                "signal_id": top_signal.signal_id,
            },
        )
        return self.build_snapshot(session)

    def pause_session(self, session: Session) -> SessionControlSnapshot:
        if self._active_session is None:
            raise ValueError("no active session")
        if self.runtime_manager.snapshot().state != RuntimeState.ACTIVE_SESSION:
            raise ValueError("runtime is not in active_session")
        # Capture payload before mutation.
        event_session_id = self._active_session.session_id
        self.runtime_manager.transition_to(RuntimeState.PAUSED)
        self._active_session.paused_at = self._clock.now()
        # write-through: persist ``paused_at`` before publishing.
        self._persist_session_state(session)
        self._write_and_publish(
            "session.paused",
            {"session_id": event_session_id},
        )
        return self.build_snapshot(session)

    def resume_session(self, session: Session) -> SessionControlSnapshot:
        if self._active_session is None:
            raise ValueError("no active session")
        if self.runtime_manager.snapshot().state != RuntimeState.PAUSED:
            raise ValueError("runtime is not paused")
        # Capture payload before mutation.
        event_session_id = self._active_session.session_id
        self.runtime_manager.transition_to(RuntimeState.ACTIVE_SESSION)
        self._active_session.paused_at = None
        # write-through: persist ``paused_at=None`` before publishing.
        self._persist_session_state(session)
        self._write_and_publish(
            "session.resumed",
            {"session_id": event_session_id},
        )
        return self.build_snapshot(session)

    def complete_session(self, session: Session) -> SessionControlSnapshot:
        if self._active_session is None:
            raise ValueError("no active session")
        state = self.runtime_manager.snapshot().state
        if state not in {RuntimeState.ACTIVE_SESSION, RuntimeState.PAUSED}:
            raise ValueError("session is not active")
        # Capture payload before clearing the active session record.
        event_session_id = self._active_session.session_id
        self.runtime_manager.transition_to(RuntimeState.REVIEW)
        # Clear in-memory, then write a full-snapshot row with all 10 fields
        # set to None. Publishing the event last ensures consumers never see
        # ``session.completed`` while the DB still holds a live row.
        self._active_session = None
        self._pending_replacement = None
        self._persist_session_state(session)
        self._write_and_publish(
            "session.completed",
            {"session_id": event_session_id},
        )
        return self.build_snapshot(session)

    def close_review(self, session: Session) -> SessionControlSnapshot:
        """Explicit operator-driven exit from REVIEW back to BACKGROUND_MONITORING.

        Closes the REVIEW-stuck gap: ``complete_session`` transitions the
        runtime to ``REVIEW`` and clears the in-memory active session, but
        no code path projects the runtime back to ``BACKGROUND_MONITORING``.
        Without this method, a second ``start_session`` after ``complete``
        returns 409 because ``can_start`` requires
        ``runtime_state != RuntimeState.REVIEW``. The only pre-existing
        workaround was a process restart.

        Operator-driven (not a side-effect of ``complete_session``) so
        that ``REVIEW`` remains a real, observable state for post-complete
        review of a session.
        """
        state = self.runtime_manager.snapshot().state
        if state != RuntimeState.REVIEW:
            raise ValueError("session is not in review")
        previous_state = state.value
        self.runtime_manager.transition_to(RuntimeState.BACKGROUND_MONITORING)
        # Idempotent: ``ops.session_state`` is already all-NULL after
        # ``complete_session``; the call keeps the write-order contract
        # uniform across the mutators.
        self._persist_session_state(session)
        self._write_and_publish(
            "session.review_closed",
            {"previous_state": previous_state},
        )
        return self.build_snapshot(session)

    def review_pair_replacement(
        self,
        session: Session,
        *,
        proposed_symbol: str | None = None,
    ) -> PairReplacementReviewSnapshot:
        if self._active_session is None:
            raise ValueError("no active session")

        signal_snapshot = self.signal_engine_service.build_snapshot(session)
        current_signal = next(
            (
                signal
                for signal in signal_snapshot.signals
                if signal.symbol == self._active_session.current_pair_symbol
            ),
            None,
        )
        candidate = self._pick_replacement_candidate(
            signal_snapshot, proposed_symbol=proposed_symbol
        )
        if candidate is None:
            raise ValueError("no replacement candidate available")
        if candidate.symbol == self._active_session.current_pair_symbol:
            raise ValueError("replacement candidate matches current pair")

        self._pending_replacement = PendingReplacementReview(
            review_id=str(uuid4()),
            current_symbol=self._active_session.current_pair_symbol,
            proposed_symbol=candidate.symbol,
            created_at=self._clock.now(),
        )
        review = self._build_replacement_review(
            current_signal=current_signal, candidate=candidate
        )
        # write-through: persist the new pending review before publishing.
        self._persist_session_state(session)
        self._write_and_publish(
            "session.replacement.reviewed",
            {
                "review_id": review.review_id,
                "current_symbol": review.current_symbol,
                "proposed_symbol": review.proposed_symbol,
            },
        )
        return review

    def apply_pair_replacement(
        self, session: Session, review_id: str
    ) -> SessionControlSnapshot:
        if self._active_session is None:
            raise ValueError("no active session")
        if (
            self._pending_replacement is None
            or self._pending_replacement.review_id != review_id
        ):
            raise ValueError("pair replacement review is missing or stale")

        signal_snapshot = self.signal_engine_service.build_snapshot(session)
        candidate = next(
            (
                signal
                for signal in signal_snapshot.signals
                if signal.symbol == self._pending_replacement.proposed_symbol
            ),
            None,
        )
        if candidate is None:
            raise ValueError("replacement candidate is no longer available")

        # Capture payload before mutating/clearing the in-memory record.
        event_session_id = self._active_session.session_id
        self._active_session.current_pair_symbol = candidate.symbol
        self._active_session.current_signal_id = candidate.signal_id
        self.workspace_service.set_focus(
            symbol=candidate.symbol,
            focus_source="session_replacement",
            signal_id=candidate.signal_id,
            session=session,
        )
        # Clear the pending record, then persist a full snapshot: the
        # updated active session with the new pair/signal and a cleared
        # pending_* set.
        self._pending_replacement = None
        self._persist_session_state(session)
        self._write_and_publish(
            "session.replacement.applied",
            {
                "session_id": event_session_id,
                "review_id": review_id,
                "symbol": candidate.symbol,
                "signal_id": candidate.signal_id,
            },
        )
        return self.build_snapshot(session)

    def _build_preflight(
        self,
        session: Session,
        signal_snapshot,
        ai_snapshot,
        *,
        for_start: bool = False,
        source_scope: Collection[str] | None = None,
    ) -> SessionPreflightSnapshot:
        control_api_ready = False
        try:
            control_api = self.runtime_manager.registry.get("control-api")
            control_api_ready = control_api.status.value in {"healthy", "degraded"}
        except KeyError:
            control_api_ready = False

        checks: list[SessionPreflightCheck] = [
            SessionPreflightCheck(
                check_id="data-freshness",
                label="Data freshness",
                status="ok"
                if signal_snapshot.market_status == "fresh"
                else "hard_fail",
                reason=(
                    "Market data is fresh enough for session start."
                    if signal_snapshot.market_status == "fresh"
                    else "Market data is degraded or stale."
                ),
                blocks_start=signal_snapshot.market_status != "fresh",
            ),
            SessionPreflightCheck(
                check_id="api-availability",
                label="API availability",
                status="ok" if control_api_ready else "hard_fail",
                reason=(
                    "Control API service is registered and available."
                    if control_api_ready
                    else "Control API service is missing or not ready."
                ),
                blocks_start=not control_api_ready,
            ),
            SessionPreflightCheck(
                check_id="active-model-loaded",
                label="Active models loaded",
                status="ok"
                if ai_snapshot.summary.degraded_role_count == 0
                else "hard_fail",
                reason=(
                    "All active AI roles are healthy."
                    if ai_snapshot.summary.degraded_role_count == 0
                    else "One or more AI roles are degraded."
                ),
                blocks_start=ai_snapshot.summary.degraded_role_count > 0,
            ),
            SessionPreflightCheck(
                check_id="shortlist-confirmed",
                label="Shortlist confirmed",
                status=(
                    "ok"
                    if any(
                        signal.state in {"active", "weakening"}
                        for signal in signal_snapshot.signals
                    )
                    else "hard_fail"
                ),
                reason=(
                    "At least one ranked signal is available."
                    if any(
                        signal.state in {"active", "weakening"}
                        for signal in signal_snapshot.signals
                    )
                    else "No ranked signal is ready for session start."
                ),
                blocks_start=not any(
                    signal.state in {"active", "weakening"}
                    for signal in signal_snapshot.signals
                ),
            ),
            SessionPreflightCheck(
                check_id="strategy-confirmed",
                label="Strategy confirmed",
                status="ok" if signal_snapshot.strategy_mode_proposal else "hard_fail",
                reason=(
                    f"Strategy proposal is {signal_snapshot.strategy_mode_proposal}."
                    if signal_snapshot.strategy_mode_proposal
                    else "No strategy mode proposal is available."
                ),
                blocks_start=not bool(signal_snapshot.strategy_mode_proposal),
            ),
        ]

        from clay.config.models import SessionLimitsConfig

        risk_config = self.config_loader.load_scope("risk")
        limits_cfg: SessionLimitsConfig = getattr(
            risk_config, "session_limits", SessionLimitsConfig()
        )

        from clay.db.repositories_demo import DEFAULT_READ_SCOPE, DemoRepository

        scope = source_scope if source_scope is not None else DEFAULT_READ_SCOPE
        demo_repo = DemoRepository(session)

        try:
            window_records = demo_repo.list_resolved_window(
                hours=limits_cfg.drawdown_window_hours, source_scope=scope
            )
            cum_pnl = round(sum(r.pnl_pct or 0.0 for r in window_records), 2)
            loss_pct = abs(cum_pnl) if cum_pnl < 0 else 0.0

            if loss_pct >= limits_cfg.max_drawdown_pct:
                checks.append(
                    SessionPreflightCheck(
                        check_id="risk-limit-drawdown",
                        label="Drawdown stop",
                        status="hard_fail",
                        reason=f"Cumulative P&L over last {limits_cfg.drawdown_window_hours}h = -{loss_pct}% exceeds max drawdown of {limits_cfg.max_drawdown_pct}%.",
                        blocks_start=True,
                    )
                )
            else:
                checks.append(
                    SessionPreflightCheck(
                        check_id="risk-limit-drawdown",
                        label="Drawdown stop",
                        status="ok",
                        reason=f"Cumulative P&L over last {limits_cfg.drawdown_window_hours}h = {cum_pnl:+.2f}% within threshold.",
                        blocks_start=False,
                    )
                )

            ordered = demo_repo.list_ordered_recent(limit=50, source_scope=scope)
            streak = 0
            streak_ts: datetime | None = None
            for r in ordered:
                if (r.pnl_pct or 0.0) < 0 and r.outcome_status in {
                    "matched",
                    "missed",
                    "late_matched",
                    "mismatched",
                }:
                    streak += 1
                    if streak_ts is None:
                        streak_ts = r.recorded_at
                else:
                    break

            now = self._clock.now()
            if streak >= limits_cfg.max_consecutive_losses and streak_ts is not None:
                if streak_ts.tzinfo is None:
                    streak_ts = streak_ts.replace(tzinfo=UTC)
                ahead = (streak_ts - now).total_seconds()
                if ahead > 60:
                    raise ValueError(
                        f"clock desync: trade recorded_at={streak_ts.isoformat()} "
                        f"ahead of clock now={now.isoformat()} by {ahead:.0f}s"
                    )
                elapsed_min = (now - streak_ts).total_seconds() / 60
                if elapsed_min < limits_cfg.cooldown_minutes:
                    remaining = int(limits_cfg.cooldown_minutes - elapsed_min)
                    checks.append(
                        SessionPreflightCheck(
                            check_id="risk-limit-cooldown",
                            label="Consecutive loss cooldown",
                            status="hard_fail",
                            reason=f"{streak} consecutive losses — cooldown active, {remaining} min remaining.",
                            blocks_start=True,
                        )
                    )
                else:
                    checks.append(
                        SessionPreflightCheck(
                            check_id="risk-limit-cooldown",
                            label="Consecutive loss cooldown",
                            status="ok",
                            reason=f"Consecutive loss check passed ({streak} loss{'es' if streak != 1 else ''} in streak, cooldown expired).",
                            blocks_start=False,
                        )
                    )
            else:
                checks.append(
                    SessionPreflightCheck(
                        check_id="risk-limit-cooldown",
                        label="Consecutive loss cooldown",
                        status="ok",
                        reason=f"Consecutive loss check passed ({streak} loss{'es' if streak != 1 else ''} in streak).",
                        blocks_start=False,
                    )
                )

            if self._active_session is not None and for_start:
                checks.append(
                    SessionPreflightCheck(
                        check_id="risk-limit-concurrent",
                        label="Max concurrent sessions",
                        status="hard_fail",
                        reason="Cannot start: active session already in progress.",
                        blocks_start=True,
                    )
                )
            elif self._active_session is not None:
                checks.append(
                    SessionPreflightCheck(
                        check_id="risk-limit-concurrent",
                        label="Max concurrent sessions",
                        status="ok",
                        reason="Active session in progress — concurrent limit respected.",
                        blocks_start=False,
                    )
                )
            else:
                checks.append(
                    SessionPreflightCheck(
                        check_id="risk-limit-concurrent",
                        label="Max concurrent sessions",
                        status="ok",
                        reason="No active session — concurrent limit clear.",
                        blocks_start=False,
                    )
                )

            open_positions = demo_repo.list_open_positions(source_scope=scope)
            total_exposure = round(
                sum(r.advisory_size_pct or 0.0 for r in open_positions), 4
            )
            block_pct = limits_cfg.max_total_exposure_block_pct
            if block_pct > 0.0 and total_exposure > block_pct:
                checks.append(
                    SessionPreflightCheck(
                        check_id="risk-limit-exposure",
                        label="Aggregate advisory exposure",
                        status="hard_fail",
                        reason=f"Total open exposure = {total_exposure}% exceeds hard block limit of {block_pct}%.",
                        blocks_start=True,
                    )
                )
            elif total_exposure > limits_cfg.max_total_exposure_pct:
                checks.append(
                    SessionPreflightCheck(
                        check_id="risk-limit-exposure",
                        label="Aggregate advisory exposure",
                        status="warn",
                        reason=f"Total open exposure = {total_exposure}% exceeds {limits_cfg.max_total_exposure_pct}% threshold.",
                        blocks_start=False,
                    )
                )
            else:
                checks.append(
                    SessionPreflightCheck(
                        check_id="risk-limit-exposure",
                        label="Aggregate advisory exposure",
                        status="ok",
                        reason=f"Total open exposure = {total_exposure}% within threshold.",
                        blocks_start=False,
                    )
                )

            active_id = (
                self._active_session.session_id if self._active_session else None
            )
            if active_id:
                session_trades = demo_repo.list_session_trades(
                    session_id=active_id, source_scope=scope
                )
                session_pnl = round(sum(r.pnl_pct or 0.0 for r in session_trades), 2)
                if (
                    session_pnl < 0
                    and abs(session_pnl) >= limits_cfg.per_session_loss_warn_pct
                ):
                    checks.append(
                        SessionPreflightCheck(
                            check_id="risk-limit-session-loss",
                            label="Per-session loss alert",
                            status="warn",
                            reason=f"Current session P&L = {session_pnl}% exceeds caution threshold of {limits_cfg.per_session_loss_warn_pct}%.",
                            blocks_start=False,
                        )
                    )
                else:
                    checks.append(
                        SessionPreflightCheck(
                            check_id="risk-limit-session-loss",
                            label="Per-session loss alert",
                            status="ok",
                            reason=f"Current session P&L = {session_pnl:+.2f}% within caution threshold.",
                            blocks_start=False,
                        )
                    )
            else:
                checks.append(
                    SessionPreflightCheck(
                        check_id="risk-limit-session-loss",
                        label="Per-session loss alert",
                        status="ok",
                        reason="No active session — per-session loss check skipped.",
                        blocks_start=False,
                    )
                )
        except Exception as exc:
            if isinstance(exc, ValueError) and "clock desync" in str(exc):
                raise
            for check_id, label in [
                ("risk-limit-drawdown", "Drawdown stop"),
                ("risk-limit-cooldown", "Consecutive loss cooldown"),
                ("risk-limit-concurrent", "Max concurrent sessions"),
                ("risk-limit-exposure", "Aggregate advisory exposure"),
                ("risk-limit-session-loss", "Per-session loss alert"),
            ]:
                checks.append(
                    SessionPreflightCheck(
                        check_id=check_id,
                        label=label,
                        status="hard_fail",
                        reason="Unable to verify risk limits due to a database error.",
                        blocks_start=True,
                    )
                )

        blockers = [check.reason for check in checks if check.blocks_start]
        return SessionPreflightSnapshot(
            status="hard_fail" if blockers else "pass",
            blocking_reason=blockers[0] if blockers else None,
            checks=checks,
        )

    def _build_briefing(self, signal_snapshot, ai_snapshot) -> SessionBriefingSnapshot:
        shortlist = [
            SessionBriefingSignal(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                direction=signal.direction,
                state=signal.state,
                confidence=signal.confidence,
                ranking_score=signal.ranking_score,
                setup_summary=signal.setup_summary,
                applied_penalties=signal.applied_penalties,
                stale_timeframes=signal.stale_timeframes,
                leader_quote_volume=signal.leader_quote_volume,
                low_quote_volume=signal.low_quote_volume,
            )
            for signal in signal_snapshot.signals[:3]
        ]
        risk_alerts = [
            f"{signal.symbol}: {trigger.title}"
            for signal in signal_snapshot.signals[:3]
            for trigger in signal.risk_triggers
        ]
        sentiment_summary = (
            "Signals show acceptable context coverage."
            if signal_snapshot.context_status == "fresh"
            else "Context coverage is thin; confidence penalties remain active."
        )
        market_context = f"Market status is {signal_snapshot.market_status}, workspace posture is {signal_snapshot.workspace_posture}."
        ai_summary = (
            f"Chief Agent uses {ai_snapshot.summary.chief_agent_model}. "
            f"Active AI conflicts: {ai_snapshot.summary.active_conflict_count}."
        )
        return SessionBriefingSnapshot(
            shortlist=shortlist,
            market_context=market_context,
            sentiment_summary=sentiment_summary,
            active_strategy=signal_snapshot.strategy_mode_proposal,
            risk_alerts=risk_alerts
            or ["No elevated risk alerts in the current shortlist."],
            ai_summary=ai_summary,
        )

    def _build_lifecycle(
        self, preflight: SessionPreflightSnapshot
    ) -> SessionLifecycleSnapshot:
        runtime_state = self.runtime_manager.snapshot().state
        if self._active_session is None and runtime_state == RuntimeState.REVIEW:
            lifecycle_state: str = "review"
        elif self._active_session is None:
            lifecycle_state: str = "idle"
        elif runtime_state == RuntimeState.PAUSED:
            lifecycle_state = "paused"
        elif runtime_state == RuntimeState.ACTIVE_SESSION:
            lifecycle_state = "active_session"
        elif runtime_state == RuntimeState.PRE_SESSION:
            lifecycle_state = "pre_session"
        else:
            lifecycle_state = "review"

        return SessionLifecycleSnapshot(
            lifecycle_state=lifecycle_state,
            runtime_state=runtime_state.value,
            session_id=self._active_session.session_id
            if self._active_session
            else None,
            current_pair_symbol=self._active_session.current_pair_symbol
            if self._active_session
            else None,
            current_signal_id=self._active_session.current_signal_id
            if self._active_session
            else None,
            started_at=self._active_session.started_at.isoformat()
            if self._active_session
            else None,
            paused_at=self._active_session.paused_at.isoformat()
            if self._active_session and self._active_session.paused_at
            else None,
            resume_ready=runtime_state == RuntimeState.PAUSED
            and self._active_session is not None,
            can_start=preflight.status == "pass"
            and self._active_session is None
            and runtime_state != RuntimeState.REVIEW,
            can_pause=runtime_state == RuntimeState.ACTIVE_SESSION
            and self._active_session is not None,
            can_resume=runtime_state == RuntimeState.PAUSED
            and self._active_session is not None,
            can_complete=runtime_state
            in {RuntimeState.ACTIVE_SESSION, RuntimeState.PAUSED}
            and self._active_session is not None,
        )

    def _build_pending_replacement(
        self, signal_snapshot
    ) -> PairReplacementReviewSnapshot | None:
        if self._pending_replacement is None or self._active_session is None:
            return None
        current_signal = next(
            (
                signal
                for signal in signal_snapshot.signals
                if signal.symbol == self._pending_replacement.current_symbol
            ),
            None,
        )
        candidate = next(
            (
                signal
                for signal in signal_snapshot.signals
                if signal.symbol == self._pending_replacement.proposed_symbol
            ),
            None,
        )
        if candidate is None:
            return None
        return self._build_replacement_review(
            current_signal=current_signal, candidate=candidate
        )

    def _pick_replacement_candidate(
        self, signal_snapshot, *, proposed_symbol: str | None
    ):
        if proposed_symbol is not None:
            return next(
                (
                    signal
                    for signal in signal_snapshot.signals
                    if signal.symbol == proposed_symbol
                ),
                None,
            )
        current_symbol = (
            self._active_session.current_pair_symbol if self._active_session else None
        )
        current_signal = next(
            (
                signal
                for signal in signal_snapshot.signals
                if signal.symbol == current_symbol
            ),
            None,
        )
        for signal in signal_snapshot.signals:
            if signal.symbol == current_symbol:
                continue
            if signal.state not in {"active", "weakening"}:
                continue
            if (
                current_signal is None
                or signal.ranking_score > current_signal.ranking_score + 0.08
            ):
                return signal
        return None

    def _build_replacement_review(
        self, *, current_signal, candidate
    ) -> PairReplacementReviewSnapshot:
        # invariant: only called from _build_pending_replacement after a
        # `self._active_session is None` guard.
        assert self._active_session is not None
        current_symbol = (
            current_signal.symbol
            if current_signal is not None
            else self._active_session.current_pair_symbol
        )
        reasons = [
            f"{candidate.symbol} ranking score is {candidate.ranking_score:.2f}.",
            f"{candidate.symbol} response action is {candidate.response_action}.",
        ]
        risks = [
            f"Focus will move away from {current_symbol}.",
            "Operator should confirm that the current pair no longer has better execution context.",
        ]
        severity = "warning" if candidate.response_action != "warning_only" else "info"
        return PairReplacementReviewSnapshot(
            review_id=self._pending_replacement.review_id
            if self._pending_replacement
            else str(uuid4()),
            current_symbol=current_symbol,
            proposed_symbol=candidate.symbol,
            severity=severity,
            summary=f"Review replacement from {current_symbol} to {candidate.symbol}.",
            reasons_to_switch=reasons,
            risks=risks,
            approval_required=True,
            blocks_apply=candidate.response_action == "block_signal",
        )

    def _write_and_publish(self, event_type: str, payload: dict[str, object]) -> None:
        self.audit_writer.write(event_type, payload)
        self.event_bus.publish("session.updated", {"event_type": event_type, **payload})
