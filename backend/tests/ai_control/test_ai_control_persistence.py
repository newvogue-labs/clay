"""Persistence tests for ``AIControlService``.

These tests exercise the Slice A3 contract:

- **First-boot:** an empty DB is seeded with ``INITIAL_ASSIGNMENTS``
  (4 rows in ``ai_assignments``) on the first ``AIControlService``
  construction.
- **Restart-survival:** an ``AIControlService`` constructed against a
  DB that has prior writes (apply / review) restores the persisted
  ``assignments`` and pending-review state instead of using defaults.
- **Write-through:** ``review_assignment`` and ``apply_assignment``
  commit their changes through the supplied ``Session``; the service's
  in-memory state stays consistent with what is on disk.

The repository layer is bypassed for some direct DB asserts (``select``
+ ``func.count()``) to keep the test honest about what was actually
written, not just what the service claims it wrote.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from clay.ai_control.service import AIControlService
from clay.db.models_ops import AIAssignment, AIControlState
from clay.db.repositories_runtime_state import (
    AIAssignmentRepository,
    AIControlStateRepository,
    INITIAL_ASSIGNMENTS,
)


def build_service(session_factory: sessionmaker) -> AIControlService:
    from clay.audit.writer import AuditWriter
    from clay.config.loader import ConfigLoader
    from clay.events.bus import EventBus
    from clay.preflight.service import PreflightService
    from clay.runtime.manager import RuntimeManager
    from clay.services.registry import ServiceRegistry

    registry = ServiceRegistry()
    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)
    config_loader = ConfigLoader()
    config_loader.ensure_default_configs()
    config_loader.load_all()
    return AIControlService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        audit_writer=AuditWriter(config_loader.paths.state_dir),
        event_bus=EventBus(),
        session_factory=session_factory,
    )


# === First-boot seeding


def test_first_boot_seeds_initial_assignments(sqlite_session_factory) -> None:
    service = build_service(sqlite_session_factory)

    assert service.assignments == dict(INITIAL_ASSIGNMENTS)
    assert set(service.assignments) == {
        "chief-agent",
        "market-scanner",
        "news-sentiment-agent",
        "forecast-model",
    }
    assert service._last_reviewed_at is None
    assert service._pending_review is None


def test_first_boot_persists_initial_assignments_to_db(sqlite_session_factory) -> None:
    build_service(sqlite_session_factory)

    with sqlite_session_factory() as session:
        repo = AIAssignmentRepository(session)
        assert repo.read_all() == dict(INITIAL_ASSIGNMENTS)
        assert session.scalar(select(func.count()).select_from(AIAssignment)) == 4


def test_first_boot_creates_singleton_ai_control_state_row(sqlite_session_factory) -> None:
    build_service(sqlite_session_factory)

    with sqlite_session_factory() as session:
        repo = AIControlStateRepository(session)
        row = repo.read()
        assert row is not None
        assert row.id == 1
        assert row.last_reviewed_at is None
        assert row.pending_review_id is None


# === Restart-survival: apply


def test_restart_survives_apply_assignment(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)

    review = service1.review_assignment(
        "forecast-model", "forecast-lite-v1", session=db_session
    )
    service1.apply_assignment(review.review_id, session=db_session)
    db_session.commit()

    # Brand-new service instance → simulates a process restart against
    # the same DB.
    service2 = build_service(sqlite_session_factory)

    assert service2.assignments["forecast-model"] == "forecast-lite-v1"
    # Other roles kept their initial mapping.
    assert service2.assignments["chief-agent"] == "minimax-m3"
    assert service2.assignments["market-scanner"] == "gemma-4-31b"
    assert service2.assignments["news-sentiment-agent"] == "gemma-4-31b"
    # Apply cleared the pending review, so the new service starts clean.
    assert service2._pending_review is None


def test_restart_picks_up_db_state_directly_via_repository(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    review = service1.review_assignment(
        "chief-agent", "gemma4:e2b-it-qat", session=db_session
    )
    service1.apply_assignment(review.review_id, session=db_session)
    db_session.commit()

    with sqlite_session_factory() as session:
        repo = AIAssignmentRepository(session)
        assert repo.read_all()["chief-agent"] == "gemma4:e2b-it-qat"


# === Restart-survival: pending review (review without apply)


def test_restart_survives_pending_review_without_apply(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    review = service1.review_assignment(
        "market-scanner", "minimax-m3", session=db_session
    )
    db_session.commit()

    service2 = build_service(sqlite_session_factory)

    assert service2._pending_review is not None
    assert service2._pending_review.review_id == review.review_id
    assert service2._pending_review.role_id == "market-scanner"
    assert service2._pending_review.model_id == "minimax-m3"
    # In-memory assignments are still the defaults (apply was not called).
    assert service2.assignments["market-scanner"] == "gemma-4-31b"


def test_pending_review_in_db_matches_in_memory_review(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service = build_service(sqlite_session_factory)
    review = service.review_assignment(
        "news-sentiment-agent", "gemma-4-31b", session=db_session
    )
    db_session.commit()

    with sqlite_session_factory() as session:
        repo = AIControlStateRepository(session)
        row = repo.read()
        assert row is not None
        assert row.pending_review_id == review.review_id
        assert row.pending_review_role_id == "news-sentiment-agent"
        assert row.pending_review_model_id == "gemma-4-31b"
        assert row.pending_review_created_at is not None
        assert row.pending_review_created_at.tzinfo is not None


# === Apply clears pending review in DB


def test_apply_clears_pending_review_columns_in_db(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service = build_service(sqlite_session_factory)
    review = service.review_assignment(
        "forecast-model", "forecast-lite-v1", session=db_session
    )
    service.apply_assignment(review.review_id, session=db_session)
    db_session.commit()

    with sqlite_session_factory() as session:
        repo = AIControlStateRepository(session)
        row = repo.read()
        assert row is not None
        assert row.pending_review_id is None
        assert row.pending_review_role_id is None
        assert row.pending_review_model_id is None
        assert row.pending_review_created_at is None
        # last_reviewed_at is preserved across apply.
        assert row.last_reviewed_at is not None


# === last_reviewed_at is preserved and restored


def test_last_reviewed_at_is_restored_after_restart(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)
    service1.review_assignment(
        "chief-agent", "gemma4:e2b-it-qat", session=db_session
    )
    db_session.commit()

    service2 = build_service(sqlite_session_factory)
    assert service2._last_reviewed_at is not None
    assert service2._last_reviewed_at.tzinfo is not None
    # last_reviewed_at reflects the most recent review, not the boot time.
    one_minute_ago = datetime.now(UTC) - timedelta(minutes=1)
    assert service2._last_reviewed_at >= one_minute_ago


# === roles / models registry stays code-only (negative test)


def test_roles_and_models_registry_are_not_persisted(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service = build_service(sqlite_session_factory)
    initial_role_count = len(service.roles)
    initial_model_count = len(service.models)

    # Mutate assignments — registry must stay unchanged.
    review = service.review_assignment(
        "forecast-model", "forecast-lite-v1", session=db_session
    )
    service.apply_assignment(review.review_id, session=db_session)
    db_session.commit()

    with sqlite_session_factory() as session:
        repo = AIAssignmentRepository(session)
        # Only one row was written: the assignment upsert.
        assert session.scalar(select(func.count()).select_from(AIAssignment)) == 4

    assert len(service.roles) == initial_role_count
    assert len(service.models) == initial_model_count


# === Multiple restarts accumulate changes


def test_multiple_restarts_preserve_all_assignment_changes(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    service1 = build_service(sqlite_session_factory)

    review1 = service1.review_assignment(
        "forecast-model", "forecast-lite-v1", session=db_session
    )
    service1.apply_assignment(review1.review_id, session=db_session)
    db_session.commit()

    service2 = build_service(sqlite_session_factory)
    review2 = service2.review_assignment(
        "chief-agent", "gemma4:e2b-it-qat", session=db_session
    )
    service2.apply_assignment(review2.review_id, session=db_session)
    db_session.commit()

    service3 = build_service(sqlite_session_factory)
    assert service3.assignments == {
        "chief-agent": "gemma4:e2b-it-qat",
        "market-scanner": "gemma-4-31b",
        "news-sentiment-agent": "gemma-4-31b",
        "forecast-model": "forecast-lite-v1",
    }


# === sanity: pending review fixture typing (helps future contributors)


def test_typing_ai_control_state_pending_columns() -> None:
    """Pending columns are populated as a group: when ``pending_review_id``
    is set, the other three pending_* columns must also be set. The
    ``AIControlState`` model exposes them with consistent ``| None`` types
    so callers can do narrowing without surprises."""
    from clay.db.models_ops import AIControlState as Model

    # Smoke-test attribute presence (catches accidental renames).
    expected = {
        "id",
        "last_reviewed_at",
        "pending_review_id",
        "pending_review_role_id",
        "pending_review_model_id",
        "pending_review_created_at",
    }
    assert expected.issubset(set(Model.__annotations__.keys()))
    # The repository's read produces a typed instance; cast keeps mypy happy.
    assert cast(type, Model) is AIControlState


# === Slice A5.5: set_assignment (trusted internal-caller path)


def test_set_assignment_persists_assignment_via_ai_assignments(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    """A5.5: ``set_assignment`` is the write-through entry point used by
    ``validation_lab.apply_activation`` for ``target_type='model_assignment'``.
    A direct call (without the validation_lab wrapper) must persist the
    new mapping to ``ai_assignments`` and survive a process restart —
    same restart-survival contract as ``apply_assignment``, but driven
    by the trusted internal path."""
    service1 = build_service(sqlite_session_factory)

    service1.set_assignment(
        role_id="forecast-model",
        model_id="forecast-lite-v1",
        session=db_session,
    )
    db_session.commit()

    # In-memory state reflects the new assignment immediately.
    assert service1.assignments["forecast-model"] == "forecast-lite-v1"
    # Other roles keep their initial mapping.
    assert service1.assignments["chief-agent"] == "minimax-m3"


    # Brand-new service instance → simulates a process restart against
    # the same DB.
    service2 = build_service(sqlite_session_factory)
    assert service2.assignments["forecast-model"] == "forecast-lite-v1"
    assert service2.assignments["chief-agent"] == "minimax-m3"
    # DB-level: the row was actually written.
    with sqlite_session_factory() as session:
        repo = AIAssignmentRepository(session)
        assert repo.read_all()["forecast-model"] == "forecast-lite-v1"


def test_set_assignment_does_not_touch_ai_control_state_pending_or_last_reviewed_at(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    """A5.5 isolation contract: ``set_assignment`` is the trusted
    internal-caller path, NOT the operator-review path. It must leave
    ``ai_control_state`` (which is owned by ``review_assignment`` /
    ``apply_assignment``) fully untouched — both ``last_reviewed_at``
    and the four ``pending_review_*`` columns.

    This keeps the semantic split crisp:
    - ``ai_control_state.last_reviewed_at`` = "when the operator last
      ran an AI-control review through the UI";
    - ``set_assignment`` = "trusted internal promotion of a validated
      config" (e.g. from ``validation_lab.apply_activation``).

    Mixing the two would conflate the trail and let validation
    promotions overwrite the operator-review timestamp.
    """
    service = build_service(sqlite_session_factory)

    # Seed ai_control_state with non-null values for both review columns
    # (a pending review that pre-dates the set_assignment call).
    review = service.review_assignment(
        role_id="chief-agent",
        model_id="gemma4:e2b-it-qat",
        session=db_session,
    )
    # Review sets last_reviewed_at AND the 4 pending_review_* columns.
    # Note: we do NOT call apply_assignment — pending stays set.
    snapshot_pending_review_id = review.review_id
    snapshot_last_reviewed_at = service._last_reviewed_at
    db_session.commit()

    # Sanity: ai_control_state row is populated as expected.
    with sqlite_session_factory() as session:
        state_before = AIControlStateRepository(session).read()
        assert state_before is not None
        assert state_before.pending_review_id == snapshot_pending_review_id
        assert state_before.last_reviewed_at == snapshot_last_reviewed_at

    # Now: set_assignment on a different role. Must NOT touch state.
    service.set_assignment(
        role_id="forecast-model",
        model_id="forecast-lite-v1",
        session=db_session,
    )
    db_session.commit()

    with sqlite_session_factory() as session:
        state_after = AIControlStateRepository(session).read()
        assert state_after is not None
        # All four pending_review_* columns must remain populated.
        assert state_after.pending_review_id == snapshot_pending_review_id
        assert state_after.pending_review_role_id == "chief-agent"
        assert state_after.pending_review_model_id == "gemma4:e2b-it-qat"
        assert state_after.pending_review_created_at is not None
        # last_reviewed_at must be unchanged (still the operator review time).
        assert state_after.last_reviewed_at == snapshot_last_reviewed_at


def test_set_assignment_validates_role_and_model(
    db_session, sqlite_session_factory: sessionmaker
) -> None:
    """A5.5 validation parity: ``set_assignment`` must run the same
    role/model validation as ``apply_assignment`` so there is a single
    source of truth for what counts as a valid assignment. Three failure
    modes (unknown role / unknown model / incompatible pair) all raise
    ``ValueError``, with NO DB write."""
    service = build_service(sqlite_session_factory)

    # Unknown role.
    with pytest.raises(ValueError, match="unknown role"):
        service.set_assignment(
            role_id="phantom-role",
            model_id="minimax-m3",
            session=db_session,
        )

    # Unknown model.
    with pytest.raises(ValueError, match="unknown model"):
        service.set_assignment(
            role_id="chief-agent",
            model_id="phantom-model",
            session=db_session,
        )

    # Incompatible pair: ``forecast-lite-v1`` is only compatible with
    # ``forecast-model``, not ``chief-agent``.
    with pytest.raises(ValueError, match="not compatible"):
        service.set_assignment(
            role_id="chief-agent",
            model_id="forecast-lite-v1",
            session=db_session,
        )

    # None of the failed attempts persisted anything.
    with sqlite_session_factory() as session:
        rows = session.scalars(select(AIAssignment)).all()
        # 4 initial rows (INITIAL_ASSIGNMENTS) and nothing else.
        assert {row.role_id for row in rows} == {
            "chief-agent",
            "market-scanner",
            "news-sentiment-agent",
            "forecast-model",
        }
        # chief-agent kept its initial model — no upsert happened.
        chief = session.get(AIAssignment, "chief-agent")
        assert chief is not None
        assert chief.model_id == "minimax-m3"


def test_set_assignment_emits_audit_and_event_with_source_validation_lab(
    db_session, sqlite_session_factory: sessionmaker, tmp_path
) -> None:
    """A5.5 trail contract: ``set_assignment`` publishes on the **same**
    ``ai.updated`` event topic as ``apply_assignment`` (so downstream
    subscribers — frontend snapshot refresh, runtime — react
    identically) but uses a **distinct** audit verb
    (``ai.assignment.set`` vs ``ai.assignment.applied``) and tags both
    audit and event payloads with ``source='validation_lab'`` for
    unambiguous triage.

    The test subscribes to a real ``EventBus`` and reads the real
    ``audit.jsonl`` file written by ``AuditWriter`` — same pattern as
    the rest of the persistence suite, no monkey-patching of service
    attributes.
    """
    import json
    from pathlib import Path

    from clay.audit.writer import AuditWriter
    from clay.config.loader import ConfigLoader
    from clay.events.bus import EventBus
    from clay.preflight.service import PreflightService
    from clay.runtime.manager import RuntimeManager
    from clay.services.registry import ServiceRegistry

    # Build a service with our own EventBus / AuditWriter so we can
    # observe their outputs (mirrors the existing test_*_persistence
    # pattern of constructing real collaborators).
    state_dir = tmp_path / "state"
    config_loader = ConfigLoader()
    config_loader.ensure_default_configs()
    config_loader.load_all()
    audit_writer = AuditWriter(state_dir)
    event_bus = EventBus()
    registry = ServiceRegistry()
    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)

    service = AIControlService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=sqlite_session_factory,
    )

    # Subscribe BEFORE the call so the queue is registered.
    queue = event_bus.subscribe()
    try:
        service.set_assignment(
            role_id="forecast-model",
            model_id="forecast-lite-v1",
            session=db_session,
        )

        # --- Event: same topic as apply_assignment, source tagged ---
        message = queue.get_nowait()
        assert message.event_type == "ai.updated"
        assert message.payload == {
            "role_id": "forecast-model",
            "previous_model_id": "gemini-3.1-flash-lite",
            "model_id": "forecast-lite-v1",
            "source": "validation_lab",
        }
        # This is NOT an operator review workflow — no review_id in payload.
        assert "review_id" not in message.payload
    finally:
        event_bus.unsubscribe(queue)

    # --- Audit: distinct verb, source tagged ---
    audit_path = Path(audit_writer.path)
    assert audit_path.exists()
    audit_lines = [json.loads(line) for line in audit_path.read_text().splitlines() if line]
    set_assignment_audits = [e for e in audit_lines if e["event_type"] == "ai.assignment.set"]
    assert len(set_assignment_audits) == 1
    assert set_assignment_audits[0]["payload"] == {
        "role_id": "forecast-model",
        "previous_model_id": "gemini-3.1-flash-lite",
        "model_id": "forecast-lite-v1",
        "source": "validation_lab",
    }
    # Cross-check: apply_assignment's verb must NOT have been emitted
    # by this path (it lives on the operator-review side only).
    applied_audits = [e for e in audit_lines if e["event_type"] == "ai.assignment.applied"]
    assert applied_audits == []
