"""A6 integration suite: end-to-end restart survival over the 6
persisted ops tables, plus ``runtime_manager`` reconciliation.

These tests run against the **production** ``build_services`` factory
on a file-based SQLite (A1-decisions). They catch bootstrap regressions
like the A6 double-init bug, where the second pass of services
silently dropped the ``session_factory`` in production while every
A3-A5 unit test still passed.

Coverage map:

- ``test_full_restart_survives_all_six_persisted_areas`` — every
  persisted area is mutated, the process is "restarted" by building a
  fresh service graph on the same DB, and every area is asserted
  restored. Includes ``ai_control_state.last_reviewed_at`` and
  ``pending_review_*`` (the operator-path side-effects of
  ``apply_assignment``, beyond the ``ai_assignments`` upsert).

- ``test_runtime_state_reconciled_to_active_session_after_restart`` —
  start a session, restart, ``runtime_manager.state ==
  ACTIVE_SESSION`` and ``lifecycle_state == "active_session"`` (not
  the false-positive ``"review"`` from the BACKGROUND_MONITORING +
  ``_active_session is not None`` fallthrough in ``_build_lifecycle``).

- ``test_runtime_state_reconciled_to_paused_session_after_restart`` —
  start + pause, restart, ``runtime_manager.state == PAUSED`` and
  ``lifecycle_state == "paused"``.

- ``test_reconcile_boot_safe_when_critical_services_not_ready`` —
  ``reconcile_to`` does NOT call ``_assert_critical_services_ready``:
  even with ``control-api = NOT_READY``, the post-restart reconcile
  is a no-exception fact, not a request. Closes the boot-safety
  concern Emma raised in A6.

The existing 5 ``test_alpha_readiness_service`` tests stay in-memory
**by design** (``build_alpha_bundle`` constructs a parallel service
graph with no ``session_factory``). This is intentional divergence —
those tests exercise the alpha-readiness logic with a fast in-memory
fixture and are not meant to be a restart-survival substitute. The
integration suite is the persistent-wiring smoke test.
"""

from __future__ import annotations

from pathlib import Path

from clay.db.repositories_runtime_state import (
    AIAssignmentRepository,
    AIControlStateRepository,
    ReliabilityStateRepository,
    SessionStateRepository,
    StrategyStateRepository,
    WorkspaceFocusRepository,
)
from clay.runtime.states import RuntimeState
from clay.services.models import ServiceStatus
from clay.validation_lab.models import ValidationRunCommand

from ._helpers import build_services_for_integration, seed_all_areas


def test_full_restart_survives_all_six_persisted_areas(tmp_path: Path) -> None:
    """Mutate all 6 persisted areas (plus ``ai_control_state``
    operator-path side-effects) → tear down → fresh service graph on
    the same DB → assert every area is restored and the alpha
    snapshot is coherent.

    This is the headline A6 acceptance: the 6 tables are
    1. ``ai_assignments`` — mutated twice (operator-path
       ``apply_assignment`` + validation-lab path
       ``set_assignment`` via ``apply_activation``);
    2. ``ai_control_state`` — operator-path
       ``review_assignment`` sets ``last_reviewed_at`` and
       ``pending_review_*``; ``apply_assignment`` clears
       ``pending_review_*``;
    3. ``session_state`` — ``start_session`` writes the active
       session row; ``review_pair_replacement`` writes a pending
       replacement;
    4. ``workspace_focus`` — explicit ``set_focus`` with
       ``focus_source="user"`` (operator, not system_recommendation);
    5. ``strategy_state`` — ``apply_activation(target_type="strategy_mode")``
       via validation_lab;
    6. ``reliability_state`` — ``recheck`` writes a fresh
       ``last_rechecked_at``.
    """
    db_path = "clay-restart-full.db"
    services1 = build_services_for_integration(tmp_path, db_filename=db_path)
    session_factory = services1["session_factory"]

    with session_factory() as session:
        seed_all_areas(session)

    ai_control = services1["ai_control_service"]
    workspace = services1["workspace_service"]
    session_control = services1["session_control_service"]
    validation_lab = services1["validation_lab_service"]
    reliability = services1["reliability_service"]

    # 1a. ai_assignments (operator path): review + apply.
    with session_factory() as session:
        review = ai_control.review_assignment(
            "chief-agent", "gemma4:e2b-it-qat", session=session
        )
        ai_control.apply_assignment(review.review_id, session=session)
        session.commit()  # A3 contract: apply_assignment flushes, caller commits.

    # 1b. ai_assignments (validation-lab path): apply_activation
    # model_assignment → set_assignment. apply_activation commits
    # internally (see validation_lab/service.py).
    with session_factory() as session:
        validation_lab.run_validation(
            session, ValidationRunCommand(run_type="model_comparison", label="promote")
        )
        review_model = validation_lab.review_activation(
            session,
            target_type="model_assignment",
            target_id="forecast-model",
            proposed_value="forecast-lite-v1",
        )
        validation_lab.apply_activation(session, review_model.review_id)

    # 3. session_state: start session + review pair replacement.
    with session_factory() as session:
        session_control.start_session(session)
        session.commit()  # A4 contract: start_session flushes, caller commits.
    with session_factory() as session:
        # review_pair_replacement may be empty if there is no candidate
        # — we only assert persistence IF a pending review was created.
        try:
            session_control.review_pair_replacement(session)
            session.commit()  # A4 contract: review_pair_replacement flushes, caller commits.
        except ValueError:
            # No replacement candidate in this seeded shortlist;
            # pending_replacement stays None which is still a valid
            # restart-survival contract.
            pass

    # 4. workspace_focus: explicit user focus (not system_recommendation).
    with session_factory() as session:
        workspace.set_focus(
            symbol="BTCUSDT",
            focus_source="user",
            signal_id=None,
            session=session,
        )
        session.commit()  # A5 contract: set_focus flushes, caller commits.

    # 5. strategy_state: apply_activation strategy_mode.
    # apply_activation commits internally.
    with session_factory() as session:
        validation_lab.run_validation(
            session, ValidationRunCommand(run_type="strategy_replay", label="switch")
        )
        review_strategy = validation_lab.review_activation(
            session,
            target_type="strategy_mode",
            target_id="global-strategy",
            proposed_value="defensive",
        )
        validation_lab.apply_activation(session, review_strategy.review_id)

    # 6. reliability_state: recheck.
    # A5 contract: recheck flushes, caller commits.
    with session_factory() as session:
        reliability.recheck(session)
        session.commit()

    # --- Capture pre-restart in-memory state for cross-checks ---
    pre_assignments = dict(ai_control.assignments)
    pre_active = session_control._active_session
    pre_pending = session_control._pending_replacement
    pre_focus_symbol = workspace._focus_symbol
    pre_focus_source = workspace._focus_source
    pre_strategy_mode = validation_lab._strategy_mode
    pre_last_rechecked_at = reliability._last_rechecked_at

    # --- DB-level snapshot of every persisted area BEFORE teardown ---
    with session_factory() as session:
        pre_ai_assignments = AIAssignmentRepository(session).read_all()
        pre_ai_state = AIControlStateRepository(session).read()
        pre_session_state = SessionStateRepository(session).read()
        pre_workspace = WorkspaceFocusRepository(session).read()
        pre_strategy = StrategyStateRepository(session).read()
        pre_reliability = ReliabilityStateRepository(session).read()

    assert pre_ai_state is not None
    assert pre_session_state is not None
    assert pre_workspace is not None
    assert pre_strategy is not None
    assert pre_reliability is not None

    # --- Teardown: drop all in-memory references to the services ---
    del services1
    del ai_control, workspace, session_control, validation_lab, reliability
    del session_factory

    # --- Restart: fresh factory on the SAME DB ---
    services2 = build_services_for_integration(tmp_path, db_filename=db_path)
    session_factory2 = services2["session_factory"]

    # 1. ai_assignments restored.
    assert services2["ai_control_service"].assignments == pre_assignments
    with session_factory2() as session:
        assert AIAssignmentRepository(session).read_all() == pre_ai_assignments

    # 2. ai_control_state: last_reviewed_at restored, pending_review_* cleared
    # (apply_assignment cleared them; the column is part of the singleton
    # row and is included in the persisted snapshot).
    with session_factory2() as session:
        post_ai_state = AIControlStateRepository(session).read()
    assert post_ai_state is not None
    assert post_ai_state.last_reviewed_at == pre_ai_state.last_reviewed_at
    assert post_ai_state.pending_review_id is None
    assert post_ai_state.pending_review_role_id is None
    assert post_ai_state.pending_review_model_id is None
    assert post_ai_state.pending_review_created_at is None
    assert services2["ai_control_service"]._last_reviewed_at is not None

    # 3. session_state restored (active_session + pending_replacement).
    active_after = services2["session_control_service"]._active_session
    pending_after = services2["session_control_service"]._pending_replacement
    if pre_active is None:
        assert active_after is None
    else:
        assert active_after is not None
        assert active_after.session_id == pre_active.session_id
        assert active_after.current_pair_symbol == pre_active.current_pair_symbol
        assert active_after.strategy_mode == pre_active.strategy_mode
    if pre_pending is None:
        assert pending_after is None
    else:
        assert pending_after is not None
        assert pending_after.review_id == pre_pending.review_id
        assert pending_after.proposed_symbol == pre_pending.proposed_symbol
    with session_factory2() as session:
        post_session_state = SessionStateRepository(session).read()
    assert post_session_state is not None
    assert post_session_state.session_id == pre_session_state.session_id

    # 4. workspace_focus restored with focus_source="user".
    assert services2["workspace_service"]._focus_symbol == pre_focus_symbol
    assert services2["workspace_service"]._focus_source == pre_focus_source
    assert services2["workspace_service"]._focus_source == "user"
    with session_factory2() as session:
        post_workspace = WorkspaceFocusRepository(session).read()
    assert post_workspace is not None
    assert post_workspace.focus_source == "user"
    assert post_workspace.focus_symbol == pre_workspace.focus_symbol
    assert post_workspace.focus_source == pre_workspace.focus_source

    # 5. strategy_state restored.
    assert services2["validation_lab_service"]._strategy_mode == pre_strategy_mode
    assert services2["validation_lab_service"]._strategy_mode == "defensive"
    with session_factory2() as session:
        post_strategy = StrategyStateRepository(session).read()
    assert post_strategy is not None
    assert post_strategy.strategy_mode == "defensive"
    assert post_strategy.strategy_mode == pre_strategy.strategy_mode

    # 6. reliability_state restored.
    assert services2["reliability_service"]._last_rechecked_at is not None
    assert services2["reliability_service"]._last_rechecked_at == pre_last_rechecked_at
    with session_factory2() as session:
        post_reliability = ReliabilityStateRepository(session).read()
    assert post_reliability is not None
    assert post_reliability.last_rechecked_at is not None
    assert post_reliability.last_rechecked_at == pre_reliability.last_rechecked_at

    # --- Alpha-readiness snapshot is coherent (not a hard-fail
    # because of in-memory drift): the brief says alpha should see
    # the restored active session and a strategy_mode update. ---
    with session_factory2() as session:
        alpha_snap = services2["alpha_readiness_service"].build_snapshot(session)
    # Session was active; lifecycle must reflect that (reconcile ran).
    assert alpha_snap.evidence.session_lifecycle_state in {
        "active_session",
        "paused",
    }


def test_runtime_state_reconciled_to_active_session_after_restart(
    tmp_path: Path,
) -> None:
    """A4 §6 Q2 / A6: after restart, a restored active session must
    produce ``lifecycle_state == "active_session"`` — not the
    false-positive ``"review"`` from the
    ``BACKGROUND_MONITORING + _active_session is not None``
    fallthrough in ``_build_lifecycle`` (session_control/service.py:514)."""
    services1 = build_services_for_integration(tmp_path, "clay-restart-active.db")
    session_factory = services1["session_factory"]
    with session_factory() as session:
        seed_all_areas(session)
    with session_factory() as session:
        services1["session_control_service"].start_session(session)
        session.commit()  # A4 contract: start_session flushes, caller commits.

    del services1

    services2 = build_services_for_integration(tmp_path, "clay-restart-active.db")
    assert services2["runtime_manager"].state == RuntimeState.ACTIVE_SESSION
    assert services2["session_control_service"]._active_session is not None
    with services2["session_factory"]() as session:
        snap = services2["session_control_service"].build_snapshot(session)
    assert snap.lifecycle.lifecycle_state == "active_session"
    assert snap.lifecycle.can_pause is True
    assert snap.lifecycle.can_complete is True


def test_runtime_state_reconciled_to_paused_session_after_restart(
    tmp_path: Path,
) -> None:
    """Same contract as the active-session test, but for
    ``paused_at is not None`` (i.e. the session was paused before the
    restart). After restart the runtime must be in ``PAUSED`` and
    ``lifecycle_state == "paused"``."""
    services1 = build_services_for_integration(tmp_path, "clay-restart-paused.db")
    session_factory = services1["session_factory"]
    with session_factory() as session:
        seed_all_areas(session)
    with session_factory() as session:
        services1["session_control_service"].start_session(session)
        session.commit()  # A4 contract: caller commits.
    with session_factory() as session:
        services1["session_control_service"].pause_session(session)
        session.commit()  # A4 contract: caller commits.

    del services1

    services2 = build_services_for_integration(tmp_path, "clay-restart-paused.db")
    assert services2["runtime_manager"].state == RuntimeState.PAUSED
    assert services2["session_control_service"]._active_session is not None
    assert services2["session_control_service"]._active_session.paused_at is not None
    with services2["session_factory"]() as session:
        snap = services2["session_control_service"].build_snapshot(session)
    assert snap.lifecycle.lifecycle_state == "paused"
    assert snap.lifecycle.can_resume is True


def test_reconcile_boot_safe_when_critical_services_not_ready(tmp_path: Path) -> None:
    """A6 boot-safety: ``RuntimeManager.reconcile_to`` (used by
    ``SessionControlService.reconcile_runtime_state``) does NOT call
    ``_assert_critical_services_ready``. Even when the control-api
    service has not yet reported HEALTHY, the post-restart reconcile
    is a no-exception fact, not a request — restoring a previously-
    active session must not block application startup.

    Scenario: build a healthy service graph, start a session, then
    simulate the ``control-api = NOT_READY`` condition by demoting
    the service status, then call ``reconcile_runtime_state``
    directly. Assert: no exception, runtime is in ``ACTIVE_SESSION``,
    lifecycle is ``"active_session"``.
    """
    services = build_services_for_integration(tmp_path, "clay-restart-bootsafe.db")
    session_factory = services["session_factory"]
    with session_factory() as session:
        seed_all_areas(session)
    with session_factory() as session:
        services["session_control_service"].start_session(session)
        session.commit()  # A4 contract: caller commits.

    # Simulate a "not-ready" critical service: control-api dropped to
    # STOPPED between the time the factory ran and the moment a
    # request handler calls reconcile. This is exactly the boot-safety
    # edge case the recon flagged (multihop via transition_to would
    # have raised RuntimeError; reconcile_to must not).
    services["registry"].update_status("control-api", ServiceStatus.STOPPED)

    # Direct reconcile call (idempotent — runtime is already
    # ACTIVE_SESSION from the factory's init-time reconcile, but we
    # call again to assert the contract holds under NOT_READY).
    services["session_control_service"].reconcile_runtime_state()

    # No exception → reconcile_to does not validate readiness.
    assert services["runtime_manager"].state == RuntimeState.ACTIVE_SESSION
    assert services["session_control_service"]._active_session is not None

    with session_factory() as session:
        snap = services["session_control_service"].build_snapshot(session)
    assert snap.lifecycle.lifecycle_state == "active_session"
