"""Tests for OverrideService (S-EXEC-3b slice 2).

Scope: service logic + state machine only. 0 API / 0 wiring / 0 LiveExecutionClient.
Config path bypassed: ExecutionConfig instantiated directly with live+allow_live_override=True.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from clay.audit.writer import AuditWriter
from clay.core.clock import SystemClock, VirtualClock
from clay.db.repositories_ops import OverrideRepository
from clay.execution.config import ExecutionConfig
from clay.execution.service import ExecutionConfigError
from clay.execution.service import OverrideService

pytestmark = pytest.mark.usefixtures("sqlite_session_factory")


def _live_config() -> ExecutionConfig:
    return ExecutionConfig(mode="live", allow_live_override=True)


def _svc(
    session_factory: sessionmaker | None = None,
    audit_writer: AuditWriter | None = None,
    clock=None,
    execution_config: ExecutionConfig | None = None,
) -> OverrideService:
    return OverrideService(
        session_factory=session_factory,
        audit_writer=audit_writer,
        clock=clock or SystemClock(),
        execution_config=execution_config or _live_config(),
    )


def _make_state(status, actor, override_id, expires_at=None):
    from clay.execution.service import _OverrideState

    return _OverrideState(
        status=status,
        actor=actor,
        expires_at=expires_at,
        override_id=override_id,
    )


def _hydrate(svc, state):
    svc._state = state


@pytest.fixture
def audit_writer(tmp_path):
    return AuditWriter(tmp_path, max_bytes=0)


# ── D5 rehydrate ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rehydrate_clears_armed_state(sqlite_session_factory):
    svc = _svc(session_factory=sqlite_session_factory)
    _hydrate(
        svc,
        _make_state(
            "confirmed",
            "op",
            "ovr_x",
            datetime.now(UTC) + timedelta(hours=1),
        ),
    )
    svc.rehydrate()
    assert svc.armed_override_id is None
    assert svc.status is None


# ── request ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_rejects_dry_run_mode():
    svc = _svc(
        execution_config=ExecutionConfig(mode="dry_run", allow_live_override=True)
    )
    with pytest.raises(ExecutionConfigError, match="mode != live"):
        await svc.request_override(actor="op", reason="test")


@pytest.mark.asyncio
async def test_request_rejects_allow_live_override_false():
    svc = _svc(execution_config=ExecutionConfig(mode="live", allow_live_override=False))
    with pytest.raises(ExecutionConfigError, match="allow_live_override=False"):
        await svc.request_override(actor="op", reason="test")


@pytest.mark.asyncio
async def test_request_rejects_existing_active_override():
    svc = _svc()
    _hydrate(
        svc,
        _make_state(
            "confirmed",
            "op",
            "ovr_x",
            datetime.now(UTC) + timedelta(hours=1),
        ),
    )
    with pytest.raises(ExecutionConfigError, match="existing active state"):
        await svc.request_override(actor="op", reason="test")


@pytest.mark.asyncio
async def test_request_returns_override_id(sqlite_session_factory):
    svc = _svc(session_factory=sqlite_session_factory)
    oid = await svc.request_override(actor="op", reason="fire drill")
    assert oid.startswith("ovr_")


@pytest.mark.asyncio
async def test_request_sets_status_pending(sqlite_session_factory):
    svc = _svc(session_factory=sqlite_session_factory)
    await svc.request_override(actor="op", reason="test")
    assert svc.status == "pending"


@pytest.mark.asyncio
async def test_request_writes_audit_db(sqlite_session_factory):
    svc = _svc(session_factory=sqlite_session_factory)
    oid = await svc.request_override(actor="op", reason="r1")
    with sqlite_session_factory() as session:
        events = OverrideRepository(session).list_by_override_id(oid)
    assert len(events) == 1
    assert events[0].action == "requested"
    assert events[0].actor == "op"


@pytest.mark.asyncio
async def test_request_writes_audit_jsonl(audit_writer):
    svc = _svc(audit_writer=audit_writer)
    await svc.request_override(actor="op", reason="r1")
    events = audit_writer.read_recent(limit=10)
    assert len(events) == 1
    assert events[0]["event_type"] == "execution.override"
    assert events[0]["payload"]["action"] == "requested"


# ── confirm ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_rejects_when_not_pending():
    svc = _svc()
    _hydrate(
        svc,
        _make_state(
            "confirmed",
            "op",
            "ovr_x",
            datetime.now(UTC) + timedelta(hours=1),
        ),
    )
    with pytest.raises(ExecutionConfigError, match="not pending"):
        await svc.confirm_override(actor="op2")


@pytest.mark.asyncio
async def test_confirm_sets_expires_at_and_confirmed(sqlite_session_factory):
    svc = _svc(session_factory=sqlite_session_factory)
    await svc.request_override(actor="op", reason="test")
    before = datetime.now(UTC)
    result = await svc.confirm_override(actor="op2")
    after = datetime.now(UTC) + timedelta(hours=1, seconds=1)

    assert result == svc._state.override_id
    assert svc.status == "confirmed"
    assert svc.expires_at is not None
    assert before <= svc.expires_at <= after


@pytest.mark.asyncio
async def test_confirm_writes_audit_db(sqlite_session_factory):
    svc = _svc(session_factory=sqlite_session_factory)
    oid = await svc.request_override(actor="op", reason="r1")
    await svc.confirm_override(actor="op2")

    with sqlite_session_factory() as session:
        events = OverrideRepository(session).list_by_override_id(oid)
    assert len(events) == 2
    assert events[1].action == "confirmed"


@pytest.mark.asyncio
async def test_confirm_writes_audit_jsonl(audit_writer):
    svc = _svc(audit_writer=audit_writer)
    await svc.request_override(actor="op", reason="r1")
    await svc.confirm_override(actor="op2")

    events = audit_writer.read_recent(limit=10)
    actions = [e["payload"]["action"] for e in events]
    assert actions == ["confirmed", "requested"]  # newest-first


# ── revoke ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_rejects_no_active_override():
    svc = _svc()
    with pytest.raises(ExecutionConfigError, match="no active override"):
        await svc.revoke_override(actor="op", reason="test")


@pytest.mark.asyncio
async def test_revoke_clears_state(sqlite_session_factory):
    svc = _svc(session_factory=sqlite_session_factory)
    await svc.request_override(actor="op", reason="test")
    await svc.confirm_override(actor="op")
    assert svc.armed_override_id is not None

    await svc.revoke_override(actor="op", reason="done")
    assert svc.armed_override_id is None
    assert svc.status is None


@pytest.mark.asyncio
async def test_revoke_writes_audit_db(sqlite_session_factory):
    svc = _svc(session_factory=sqlite_session_factory)
    oid = await svc.request_override(actor="op", reason="r1")
    await svc.confirm_override(actor="op")
    await svc.revoke_override(actor="op", reason="done")

    with sqlite_session_factory() as session:
        events = OverrideRepository(session).list_by_override_id(oid)
    assert [e.action for e in events] == ["requested", "confirmed", "revoked"]


@pytest.mark.asyncio
async def test_revoke_writes_audit_jsonl(audit_writer):
    svc = _svc(audit_writer=audit_writer)
    await svc.request_override(actor="op", reason="r1")
    await svc.confirm_override(actor="op")
    await svc.revoke_override(actor="op", reason="done")

    events = audit_writer.read_recent(limit=10)
    actions = [e["payload"]["action"] for e in events]
    assert actions == ["revoked", "confirmed", "requested"]  # newest-first


# ── maybe_expire ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pending_not_expired():
    clock = VirtualClock(start=datetime(2026, 6, 27, tzinfo=UTC))
    svc = _svc(clock=clock)
    _hydrate(svc, _make_state("pending", "op", "ovr_x"))
    result = await svc.maybe_expire()
    assert result is None


@pytest.mark.asyncio
async def test_confirmed_not_expired_before_ttl():
    clock = VirtualClock(start=datetime(2026, 6, 27, tzinfo=UTC))
    svc = _svc(clock=clock)
    _hydrate(
        svc,
        _make_state(
            "confirmed",
            "op",
            "ovr_x",
            clock.now() + timedelta(hours=1),
        ),
    )
    result = await svc.maybe_expire()
    assert result is None
    assert svc.status == "confirmed"


@pytest.mark.asyncio
async def test_confirmed_expires_after_ttl(audit_writer):
    clock = VirtualClock(start=datetime(2026, 6, 27, tzinfo=UTC))
    svc = _svc(clock=clock, audit_writer=audit_writer)
    _hydrate(
        svc,
        _make_state(
            "confirmed",
            "op",
            "ovr_x",
            clock.now() + timedelta(hours=1),
        ),
    )
    clock.tick(timedelta(hours=1, seconds=1))
    result = await svc.maybe_expire()
    assert result == "ovr_x"
    assert svc.status is None
    assert svc.armed_override_id is None


@pytest.mark.asyncio
async def test_expired_not_live_eligible():
    clock = VirtualClock(start=datetime(2026, 6, 27, tzinfo=UTC))
    svc = _svc(clock=clock)
    _hydrate(
        svc,
        _make_state(
            "confirmed",
            "op",
            "ovr_x",
            clock.now() + timedelta(hours=1),
        ),
    )
    clock.tick(timedelta(hours=1, seconds=1))
    await svc.maybe_expire()
    assert svc.is_live_eligible() is False


# ── is_live_eligible (D2/D7) ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_live_eligible_confirmed_not_expired():
    clock = SystemClock()
    svc = _svc(clock=clock)
    _hydrate(
        svc,
        _make_state(
            "confirmed",
            "op",
            "ovr_x",
            clock.now() + timedelta(hours=1),
        ),
    )
    assert svc.is_live_eligible() is True


@pytest.mark.asyncio
async def test_not_live_eligible_no_active_override():
    svc = _svc()
    assert svc.is_live_eligible() is False


@pytest.mark.asyncio
async def test_not_live_eligible_dry_run():
    svc = _svc(
        execution_config=ExecutionConfig(mode="dry_run", allow_live_override=True)
    )
    _hydrate(
        svc,
        _make_state(
            "confirmed",
            "op",
            "ovr_x",
            datetime.now(UTC) + timedelta(hours=1),
        ),
    )
    assert svc.is_live_eligible() is False


@pytest.mark.asyncio
async def test_not_live_eligible_expired():
    clock = VirtualClock(start=datetime(2026, 6, 27, tzinfo=UTC))
    svc = _svc(clock=clock)
    _hydrate(
        svc,
        _make_state(
            "confirmed",
            "op",
            "ovr_x",
            clock.now() + timedelta(hours=1),
        ),
    )
    clock.tick(timedelta(hours=1, seconds=1))
    assert svc.is_live_eligible() is False


@pytest.mark.asyncio
async def test_not_live_eligible_pending():
    svc = _svc()
    _hydrate(svc, _make_state("pending", "op", "ovr_x"))
    assert svc.is_live_eligible() is False


# ── full lifecycle ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_lifecycle_request_confirm_revoke(sqlite_session_factory):
    svc = _svc(session_factory=sqlite_session_factory)

    oid = await svc.request_override(actor="op_a", reason="fire drill")
    assert svc.status == "pending"

    await svc.confirm_override(actor="op_b")
    assert svc.status == "confirmed"
    assert svc.armed_override_id == oid

    await svc.revoke_override(actor="op_a", reason="all clear")
    assert svc.status is None
    assert svc.armed_override_id is None

    with sqlite_session_factory() as session:
        events = OverrideRepository(session).list_by_override_id(oid)
    assert [e.action for e in events] == ["requested", "confirmed", "revoked"]


# ── manual-only (D4) ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_is_explicit_no_auto():
    svc = _svc()
    await svc.request_override(actor="op", reason="test")
    # Status stays pending until explicit confirm() call
    assert svc.status == "pending"
    assert svc.armed_override_id is None


@pytest.mark.asyncio
async def test_revoke_is_explicit_no_auto():
    svc = _svc()
    await svc.request_override(actor="op", reason="test")
    await svc.confirm_override(actor="op")
    # Status stays confirmed until explicit revoke() call
    assert svc.status == "confirmed"
    assert svc.armed_override_id is not None


# ── restart-collision regression (BLOCKER M246) ───────────────────────────


@pytest.mark.asyncio
async def test_event_ids_remain_unique_after_service_restart(
    sqlite_session_factory,
) -> None:
    """Simulate backend restart: re-instantiate service, request twice.

    Ensures _make_event_id() (now uuid4) never collides across instances.
    """
    svc1 = _svc(session_factory=sqlite_session_factory)
    oid1 = await svc1.request_override(actor="op", reason="r1")
    await svc1.confirm_override(actor="op")

    svc2 = _svc(session_factory=sqlite_session_factory)
    oid2 = await svc2.request_override(actor="op", reason="r2")
    await svc2.confirm_override(actor="op")

    with sqlite_session_factory() as session:
        events1 = OverrideRepository(session).list_by_override_id(oid1)
        events2 = OverrideRepository(session).list_by_override_id(oid2)

    all_ids = [e.event_id for e in events1 + events2]
    assert len(all_ids) == 4
    assert len(set(all_ids)) == 4, "event_id collision after simulated restart"


# ── D-12c: pre-arm reconcile hook ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_no_hook_passes_through(sqlite_session_factory):
    """Without a pre-arm hook, confirm_override behaves as before (no-op)."""
    svc = _svc(session_factory=sqlite_session_factory)
    await svc.request_override(actor="op", reason="test")
    result = await svc.confirm_override(actor="op2")
    assert svc.status == "confirmed"
    assert result == svc._state.override_id


@pytest.mark.asyncio
async def test_confirm_clean_hook_allows(sqlite_session_factory):
    """Pre-arm hook returning False (clean) → confirm proceeds."""
    svc = _svc(session_factory=sqlite_session_factory)
    hook_called = []

    async def clean_hook() -> bool:
        hook_called.append(True)
        return False

    svc.set_pre_arm_reconcile(clean_hook)
    await svc.request_override(actor="op", reason="test")
    await svc.confirm_override(actor="op2")

    assert svc.status == "confirmed"
    assert len(hook_called) == 1


@pytest.mark.asyncio
async def test_confirm_fatal_hook_denies(sqlite_session_factory):
    """Pre-arm hook returning True (fatal) → confirm denied, audit written."""
    svc = _svc(session_factory=sqlite_session_factory)

    async def fatal_hook() -> bool:
        return True

    svc.set_pre_arm_reconcile(fatal_hook)
    await svc.request_override(actor="op", reason="test")

    with pytest.raises(ExecutionConfigError, match="arm denied"):
        await svc.confirm_override(actor="op2")

    # Status remains pending (not confirmed)
    assert svc.status == "pending"

    # Audit: arm_denied_reconcile
    override_id = svc._state.override_id
    assert override_id is not None
    with sqlite_session_factory() as session:
        events = OverrideRepository(session).list_by_override_id(override_id)
    denied = [e for e in events if e.action == "arm_denied_reconcile"]
    assert len(denied) == 1


@pytest.mark.asyncio
async def test_confirm_hook_exception_denies(sqlite_session_factory):
    """Pre-arm hook raising → fail-closed (deny)."""
    svc = _svc(session_factory=sqlite_session_factory)

    async def broken_hook() -> bool:
        raise RuntimeError("db connection lost")

    svc.set_pre_arm_reconcile(broken_hook)
    await svc.request_override(actor="op", reason="test")

    with pytest.raises(ExecutionConfigError, match="arm denied"):
        await svc.confirm_override(actor="op2")

    assert svc.status == "pending"


@pytest.mark.asyncio
async def test_set_pre_arm_reconcile_replaces_hook():
    """set_pre_arm_reconcile replaces the previous hook."""
    svc = _svc()

    call_log = []

    async def hook1() -> bool:
        call_log.append("hook1")
        return True

    async def hook2() -> bool:
        call_log.append("hook2")
        return False

    svc.set_pre_arm_reconcile(hook1)
    svc.set_pre_arm_reconcile(hook2)
    # We can't easily call confirm without going through request,
    # but the hook replacement is the key invariant.
    assert svc._pre_arm_reconcile is hook2
