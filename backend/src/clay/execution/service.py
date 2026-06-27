from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import sessionmaker

from clay.audit.writer import AuditWriter
from clay.core.clock import Clock, SystemClock
from clay.db.models_ops import ExecutionOverride
from clay.db.repositories_ops import OverrideRepository
from clay.execution.config import ExecutionConfig
from clay.execution.exceptions import ExecutionConfigError


logger = logging.getLogger(__name__)

OVERRIDE_TTL = timedelta(hours=1)


@dataclass
class _OverrideState:
    """Internal mutable override lifecycle state machine.

    Transitions:
        None ──request──► pending ──confirm──► confirmed ──revoke──► None
                                       └──expire──► expired(None)
    """

    status: str | None = None  # None | pending | confirmed | expired
    actor: str | None = None
    expires_at: datetime | None = None
    override_id: str | None = None


class OverrideService:
    """Manages execution override lifecycle (S-EXEC-3b).

    Ownership responsibilities:
    - DB audit journal: ``ops.execution_overrides`` via ``OverrideRepository``
      (source of truth for history + rehydrate)
    - JSONL observability: ``audit_writer.write()`` (secondary, never rehydrate
      source)

    Decree D5 (default-deny): ``_rehydrate_from_db`` reconstructs ONLY
    history; armed ``_state`` is ALWAYS ``None`` after restart — no implicit
    resurrection from ``expires_at > now``.

    Decree D4 (manual-only): ``request``/``confirm``/``revoke`` are explicit
    operator actions — never auto-called from advisory, signal, scheduler, or
    agent paths.

    two-person rule is NOT enforced (``require_distinct_confirmer=False``).
    Two-step friction (separate request+confirm timestamps+actors) provides
    the audit trail without coupling WorkspaceService.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker | None = None,
        audit_writer: AuditWriter | None = None,
        clock: Clock = SystemClock(),
        execution_config: ExecutionConfig | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._audit_writer = audit_writer
        self._clock = clock
        self._execution_config = execution_config
        self._state: _OverrideState = _OverrideState()

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def rehydrate(self) -> None:
        """Clear in-memory override state on startup.

        Decree D5: armed state is ALWAYS None after restart.
        Re-arm requires an explicit ``request`` → ``confirm`` cycle.
        """
        self._state = _OverrideState()

    async def request_override(
        self,
        *,
        actor: str,
        reason: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Step 1 of override lifecycle: transitions None → pending.

        Preconditions ( enforced):
        - mode == "live"
        - allow_live_override config is True
        - no active armed state (not pending, not confirmed)

        Returns the new override_id.
        """
        if not self._is_live_config():
            raise ExecutionConfigError(
                "override request rejected: mode != live or "
                "allow_live_override=False"
            )
        if self._state.status is not None:
            raise ExecutionConfigError(
                f"override request rejected: existing active state "
                f"status={self._state.status!r}"
            )

        override_id = f"ovr_{self._clock.now().strftime('%Y%m%d_%H%M%S_%f')}"
        self._state = _OverrideState(
            status="pending", actor=actor, override_id=override_id
        )

        await self._append_audit(
            override_id=override_id,
            actor=actor,
            action="requested",
            mode_before=None,
            mode_after="live",
            expires_at=None,
            reason=reason,
            session_id=session_id,
        )

        logger.info(
            "override requested id=%s actor=%s session=%s",
            override_id, actor, session_id,
        )
        return override_id

    async def confirm_override(
        self,
        *,
        actor: str,
        ttl: timedelta = OVERRIDE_TTL,
        reason: str | None = None,
    ) -> str:
        """Step 2 of override lifecycle: transitions pending → confirmed.

        Preconditions ( enforced):
        - current status == "pending"
        """
        if self._state.status != "pending":
            raise ExecutionConfigError(
                f"confirm rejected: override not pending "
                f"(status={self._state.status!r})"
            )

        override_id = self._state.override_id
        expires_at = self._clock.now() + ttl
        self._state = _OverrideState(
            status="confirmed",
            actor=actor,
            expires_at=expires_at,
            override_id=override_id,
        )

        await self._append_audit(
            override_id=override_id,
            actor=actor,
            action="confirmed",
            mode_before="live",
            mode_after="live",
            expires_at=expires_at,
            reason=reason,
        )

        logger.info(
            "override confirmed id=%s actor=%s expires=%s",
            override_id, actor, expires_at.isoformat(),
        )
        return override_id

    async def revoke_override(self, *, actor: str, reason: str | None = "") -> str:
        """Explicit revocation: transitions None ← confirmed/pending.

        Decree D4: manual-only, explicit operator action.
        """
        if self._state.status is None:
            raise ExecutionConfigError(
                "revoke rejected: no active override to revoke"
            )

        override_id = self._state.override_id
        prev_status = self._state.status
        self._state = _OverrideState()

        await self._append_audit(
            override_id=override_id,
            actor=actor,
            action="revoked",
            mode_before="live",
            mode_after="live",
            reason=reason,
        )

        logger.info(
            "override revoked id=%s prev_status=%s actor=%s",
            override_id, prev_status, actor,
        )
        return override_id

    async def maybe_expire(self) -> str | None:
        """Lazy expiry check: transitions confirmed → expired if TTL elapsed.

        Called explicitly before live-mode gate decisions — never auto-fired.
        Returns the override_id if an expiry was recorded, else None.
        """
        if self._state.status != "confirmed":
            return None
        if self._state.expires_at is None:
            return None
        if self._clock.now() < self._state.expires_at:
            return None

        override_id = self._state.override_id
        expired_at = self._state.expires_at
        self._state = _OverrideState()

        await self._append_audit(
            override_id=override_id,
            actor="system",
            action="expired",
            mode_before="live",
            mode_after="live",
            expires_at=expired_at,
            reason="ttl elapsed",
        )

        logger.info("override expired id=%s", override_id)
        return override_id

    # ── queries ────────────────────────────────────────────────────────────

    @property
    def armed_override_id(self) -> str | None:
        """Returns override_id if confirmed and not expired, else None."""
        if self._state.status != "confirmed":
            return None
        if self._state.expires_at is not None and self._clock.now() >= self._state.expires_at:
            return None
        return self._state.override_id

    def is_live_eligible(self) -> bool:
        """Computable predicate for live-mode gate (D2/D7).

        Eligible iff:
          mode == "live" AND confirmed AND not expired AND not degraded

        The predicate is DRY — callers check before every live action.
        Degraded mode keeps the service INERT even if confirmed.
        """
        if not self._is_live_config():
            return False
        if self._state.status != "confirmed":
            return False
        if self._state.expires_at is not None and self._clock.now() >= self._state.expires_at:
            return False
        return not self._is_degraded()

    def is_degraded(self) -> bool:
        """Explicit degraded check for consumers (D7)."""
        return self._is_degraded()

    # ── private ────────────────────────────────────────────────────────────

    def _is_live_config(self) -> bool:
        if self._execution_config is None:
            return False
        if self._execution_config.mode != "live":
            return False
        if not self._execution_config.allow_live_override:
            return False
        return True

    def _is_degraded(self) -> bool:
        # Degraded = proactive killswitch engaged; live+pending → inert.
        # Extended by 3b-3 / 3b-4 for session/connector degradation signals.
        return False

    async def _append_audit(
        self,
        *,
        override_id: str,
        actor: str,
        action: str,
        mode_before: str | None,
        mode_after: str | None,
        expires_at: datetime | None = None,
        reason: str | None = None,
        session_id: str | None = None,
    ) -> None:
        event_id = str(uuid4())
        event = ExecutionOverride(
            event_id=event_id,
            override_id=override_id,
            actor=actor,
            action=action,
            mode_before=mode_before,
            mode_after=mode_after,
            expires_at=expires_at,
            reason=reason,
            created_at=self._clock.now(),
            audit_id=None,
        )

        if self._session_factory is not None:
            with self._session_factory() as session:
                repo = OverrideRepository(session)
                repo.append(event)
                session.commit()

        if self._audit_writer is not None:
            self._audit_writer.write(
                "execution.override",
                {
                    "event_id": event_id,
                    "override_id": override_id,
                    "actor": actor,
                    "action": action,
                    "mode_before": mode_before,
                    "mode_after": mode_after,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "reason": reason,
                    "session_id": session_id,
                },
            )


