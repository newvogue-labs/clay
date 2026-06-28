"""Concrete SQL implementation of ProviderPoolRepository.

Implements the protocol from ``provider_pool.py`` via SQLAlchemy ORM
against ``ops.provider*`` tables.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from clay.ai_control.provider_pool import (
    Deployment,
    DeploymentRow,
    HealthOutcome,
    ProviderKey,
    ProviderPoolRepository,
    KeyState,
)

KEY_COLS = [
    "k.id",
    "k.provider_id",
    "k.account_label",
    "k.key_ref",
    "k.state",
    "k.consecutive_fails",
    "k.last_outcome",
    "k.cooling_until",
    "k.reset_at",
    "k.reset_tz",
    "k.rpm_limit",
    "k.rpd_limit",
    "k.rpd_used",
    "k.daily_token_limit",
    "k.daily_token_used",
]

DEP_COLS = [
    "d.id",
    "d.model_name",
    "d.provider_key_id",
    "d.upstream_model",
    "d.params",
    "d.weight",
    "d.enabled",
]


def _row_to_key(row) -> ProviderKey:
    return ProviderKey(
        id=row.id,
        provider_id=row.provider_id,
        account_label=row.account_label,
        key_ref=row.key_ref,
        state=KeyState(row.state),
        consecutive_fails=row.consecutive_fails,
        last_outcome=HealthOutcome(row.last_outcome) if row.last_outcome else None,
        cooling_until=row.cooling_until,
        reset_at=row.reset_at,
        reset_tz=row.reset_tz,
        rpm_limit=row.rpm_limit,
        rpd_limit=row.rpd_limit,
        rpd_used=row.rpd_used,
        daily_token_limit=row.daily_token_limit,
        daily_token_used=row.daily_token_used,
    )


def _row_to_dep(row) -> Deployment:
    return Deployment(
        id=row.id,
        model_name=row.model_name,
        provider_key_id=row.provider_key_id,
        upstream_model=row.upstream_model,
        params=row.params
        if isinstance(row.params, dict)
        else json.loads(row.params or "{}"),
        weight=row.weight,
        enabled=row.enabled,
    )


_SELECT_DEPLOYMENTS = f"""
SELECT {", ".join(DEP_COLS)} FROM ops.provider_deployment d
WHERE d.enabled = true
"""


class SqlProviderPoolRepository(ProviderPoolRepository):
    """SQL-backed repository for ProviderPool.

    Uses raw SQL via ``Session.execute()`` to stay decoupled from the
    ORM model layer (provider* tables have no ORM models — S1 was DDL-only).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_available_for_model(self, model_name: str) -> Sequence[Deployment]:
        sql = _SELECT_DEPLOYMENTS + " AND d.model_name = :name"
        rows = self._session.execute(text(sql), {"name": model_name}).all()
        return [_row_to_dep(r) for r in rows]

    def get_deployment(self, deployment_id: int) -> Deployment | None:
        sql = _SELECT_DEPLOYMENTS + " AND d.id = :id"
        row = self._session.execute(text(sql), {"id": deployment_id}).one_or_none()
        return _row_to_dep(row) if row is not None else None

    def get_key(self, key_id: int | None) -> ProviderKey | None:
        if key_id is None:
            return None
        sql = f"SELECT {', '.join(KEY_COLS)} FROM ops.provider_key k WHERE k.id = :id"
        row = self._session.execute(text(sql), {"id": key_id}).one_or_none()
        return _row_to_key(row) if row is not None else None

    def update_key(self, key_id: int, **updates: object) -> None:
        if not updates:
            return
        sets = ", ".join(f"{k} = :{k}" for k in updates)
        sql = f"UPDATE ops.provider_key SET {sets} WHERE id = :id"
        self._session.execute(text(sql), {"id": key_id, **updates})
        self._session.flush()

    def insert_health(
        self,
        *,
        provider_key_id: int | None,
        deployment_id: int | None,
        model_name: str,
        outcome: HealthOutcome,
        latency_ms: int | None,
        tokens: int | None,
        error_excerpt: str | None,
        time: datetime,
    ) -> None:
        sql = """
        INSERT INTO ops.provider_health
            (time, provider_key_id, deployment_id, model_name, outcome, latency_ms, tokens, error_excerpt)
        VALUES
            (:time, :provider_key_id, :deployment_id, :model_name, :outcome, :latency_ms, :tokens, :error_excerpt)
        """
        self._session.execute(
            text(sql),
            {
                "time": time,
                "provider_key_id": provider_key_id,
                "deployment_id": deployment_id,
                "model_name": model_name,
                "outcome": outcome.value,
                "latency_ms": latency_ms,
                "tokens": tokens,
                "error_excerpt": error_excerpt,
            },
        )
        self._session.flush()

    def expire_cooling(self, now: datetime) -> int:
        sql = """
        UPDATE ops.provider_key
        SET state = 'available', cooling_until = NULL
        WHERE state = 'cooling' AND cooling_until <= :now
        """
        result = self._session.execute(text(sql), {"now": now})
        self._session.flush()
        return result.rowcount

    def expire_exhausted(self, now: datetime) -> int:
        sql = """
        UPDATE ops.provider_key
        SET state = 'available', rpd_used = 0, daily_token_used = 0
        WHERE state = 'exhausted' AND reset_at <= :now
        """
        result = self._session.execute(text(sql), {"now": now})
        self._session.flush()
        return result.rowcount

    def list_enabled_deployments(self) -> Sequence[DeploymentRow]:
        sql = """
        SELECT
            d.id AS deployment_id,
            d.model_name,
            d.upstream_model,
            p.base_url,
            k.key_ref,
            k.state AS key_state,
            d.params
        FROM ops.provider_deployment d
        JOIN ops.provider p ON p.id = d.provider_id
        LEFT JOIN ops.provider_key k ON k.id = d.provider_key_id
        WHERE d.enabled = true
        ORDER BY d.model_name
        """
        rows = self._session.execute(text(sql)).all()
        return [
            DeploymentRow(
                deployment_id=r.deployment_id,
                model_name=r.model_name,
                upstream_model=r.upstream_model,
                base_url=r.base_url,
                key_ref=r.key_ref,
                key_state=r.key_state,
                params=r.params
                if isinstance(r.params, dict)
                else json.loads(r.params or "{}"),
            )
            for r in rows
        ]
