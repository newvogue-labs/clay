"""Write-through repositories for the 6 ops runtime-state tables.

See alembic revision 0008_ops_runtime_state and the 6 ORM models in
clay.db.models_ops. Five of the tables are singletons (``CHECK id = 1``);
``ai_assignments`` is multi-row keyed by ``role_id``.

Conventions follow the existing repositories in this package (see
``clay.db.repositories_ops.OpsRepository`` for the canonical pattern):
the ``Session`` is injected, mutations call ``flush()`` (never
``commit()``), and reads use ``select(...).scalars()`` or
``session.get(model, pk)``.

Datetime defaults (``updated_at``) are written by these helpers via
``datetime.now(UTC)`` because the ORM models intentionally do not
duplicate the server-side ``CURRENT_TIMESTAMP`` defaults from the
migration — pytest exercises the model layer through
``Base.metadata.create_all()`` where server defaults are not applied.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from clay.db.models_ops import (
    AIAssignment,
    AIControlState,
    ReliabilityState,
    SessionState,
    StrategyState,
    WorkspaceFocus,
)


TModel = TypeVar("TModel")


INITIAL_ASSIGNMENTS: dict[str, str] = {
    "chief-agent": "minimax-m3",
    "market-scanner": "gemma-4-31b",
    "news-sentiment-agent": "gemma-4-31b",
    "forecast-model": "gemini-3.1-flash-lite",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _singleton_get_or_create(
    session: Session,
    model: type[TModel],
    *,
    defaults: dict[str, Any] | None = None,
    with_updated_at: bool = False,
) -> TModel:
    row = session.get(model, 1)
    if row is not None:
        return row
    payload: dict[str, Any] = {"id": 1, **(defaults or {})}
    if with_updated_at:
        payload["updated_at"] = _utcnow()
    row = model(**payload)
    session.add(row)
    session.flush()
    return row


def _singleton_save(
    session: Session,
    model: type[TModel],
    fields: dict[str, Any],
    *,
    defaults: dict[str, Any] | None = None,
    with_updated_at: bool = False,
) -> None:
    row = session.get(model, 1)
    if row is None:
        payload: dict[str, Any] = {"id": 1, **(defaults or {}), **fields}
        if with_updated_at:
            payload["updated_at"] = _utcnow()
        row = model(**payload)
        session.add(row)
    else:
        for key, value in fields.items():
            setattr(row, key, value)
        if with_updated_at:
            row.updated_at = _utcnow()
    session.flush()


def _singleton_read(session: Session, model: type[TModel]) -> TModel | None:
    return session.get(model, 1)


class AIAssignmentRepository:
    """Multi-row repository for role -> model assignments."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def read_all(self) -> dict[str, str]:
        query = select(AIAssignment)
        return {row.role_id: row.model_id for row in self.session.scalars(query).all()}

    def upsert(self, role_id: str, model_id: str) -> None:
        existing = self.session.get(AIAssignment, role_id)
        if existing is None:
            self.session.add(
                AIAssignment(
                    role_id=role_id,
                    model_id=model_id,
                    updated_at=_utcnow(),
                ),
            )
        else:
            existing.model_id = model_id
            existing.updated_at = _utcnow()
        self.session.flush()

    def bulk_upsert(self, mapping: dict[str, str]) -> None:
        for role_id, model_id in mapping.items():
            self.upsert(role_id, model_id)


class AIControlStateRepository:
    """Singleton repository for AIControlState (id=1)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def read(self) -> AIControlState | None:
        return _singleton_read(self.session, AIControlState)

    def get_or_create(self) -> AIControlState:
        return _singleton_get_or_create(self.session, AIControlState)

    def save(self, **fields: Any) -> None:
        _singleton_save(self.session, AIControlState, fields)


class SessionStateRepository:
    """Singleton repository for SessionState (id=1)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def read(self) -> SessionState | None:
        return _singleton_read(self.session, SessionState)

    def get_or_create(self) -> SessionState:
        return _singleton_get_or_create(self.session, SessionState)

    def save(self, **fields: Any) -> None:
        _singleton_save(self.session, SessionState, fields)


class WorkspaceFocusRepository:
    """Singleton repository for WorkspaceFocus (id=1).

    Default ``focus_source`` is ``"system_recommendation"`` (mirrors the
    server-side default in alembic revision 0008).
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def read(self) -> WorkspaceFocus | None:
        return _singleton_read(self.session, WorkspaceFocus)

    def get_or_create(self) -> WorkspaceFocus:
        return _singleton_get_or_create(
            self.session,
            WorkspaceFocus,
            defaults={"focus_source": "system_recommendation"},
            with_updated_at=True,
        )

    def save(self, **fields: Any) -> None:
        _singleton_save(
            self.session,
            WorkspaceFocus,
            fields,
            defaults={"focus_source": "system_recommendation"},
            with_updated_at=True,
        )


class StrategyStateRepository:
    """Singleton repository for StrategyState (id=1).

    Default ``strategy_mode`` is ``"momentum"`` (mirrors the server-side
    default in alembic revision 0008).
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def read(self) -> StrategyState | None:
        return _singleton_read(self.session, StrategyState)

    def get_or_create(self) -> StrategyState:
        return _singleton_get_or_create(
            self.session,
            StrategyState,
            defaults={"strategy_mode": "momentum"},
            with_updated_at=True,
        )

    def save(self, **fields: Any) -> None:
        _singleton_save(
            self.session,
            StrategyState,
            fields,
            defaults={"strategy_mode": "momentum"},
            with_updated_at=True,
        )


class ReliabilityStateRepository:
    """Singleton repository for ReliabilityState (id=1)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def read(self) -> ReliabilityState | None:
        return _singleton_read(self.session, ReliabilityState)

    def get_or_create(self) -> ReliabilityState:
        return _singleton_get_or_create(self.session, ReliabilityState)

    def save(self, **fields: Any) -> None:
        _singleton_save(self.session, ReliabilityState, fields)
