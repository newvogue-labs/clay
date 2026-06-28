"""ProviderPool — resource manager for provider API keys (S2).

FSM-таблица из ADR-013-addendum. Чистая логика, 0 behavior-drift.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, Sequence


class HealthOutcome(str, enum.Enum):
    SUCCESS = "success"
    AUTH_FAIL = "auth_fail"
    QUOTA = "quota"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    BAD_REQUEST = "bad_request"
    UPSTREAM = "upstream"


class KeyState(str, enum.Enum):
    AVAILABLE = "available"
    COOLING = "cooling"
    EXHAUSTED = "exhausted"
    DEAD = "dead"


_SOFT_FAILS = frozenset({HealthOutcome.TIMEOUT, HealthOutcome.UPSTREAM})


@dataclass
class ProviderKey:
    id: int
    provider_id: int
    account_label: str
    key_ref: str
    state: KeyState
    consecutive_fails: int
    last_outcome: HealthOutcome | None
    cooling_until: datetime | None
    reset_at: datetime | None
    reset_tz: str | None
    rpm_limit: int | None
    rpd_limit: int | None
    rpd_used: int
    daily_token_limit: int | None
    daily_token_used: int


@dataclass
class Deployment:
    id: int
    model_name: str
    provider_key_id: int | None
    upstream_model: str
    params: dict
    weight: int
    enabled: bool


@dataclass
class DeploymentWithKey:
    deployment: Deployment
    key: ProviderKey | None


@dataclass
class DeploymentRow:
    """Merged view for rendering: deployment + provider + key."""

    deployment_id: int
    model_name: str
    upstream_model: str
    base_url: str | None
    key_ref: str | None
    key_state: str | None
    params: dict


class ProviderPoolRepository(Protocol):
    def get_available_for_model(self, model_name: str) -> Sequence[Deployment]: ...

    def get_deployment(self, deployment_id: int) -> Deployment | None: ...

    def get_key(self, key_id: int | None) -> ProviderKey | None: ...

    def update_key(self, key_id: int, **updates: object) -> None: ...

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
    ) -> None: ...

    def expire_cooling(self, now: datetime) -> int: ...

    def expire_exhausted(self, now: datetime) -> int: ...

    def list_enabled_deployments(self) -> Sequence[DeploymentRow]: ...


class ProviderPool:
    def __init__(
        self,
        repo: ProviderPoolRepository,
        *,
        allowed_fails: int = 2,
        cooldown: timedelta = timedelta(hours=6),
    ) -> None:
        self._repo = repo
        self._allowed_fails = allowed_fails
        self._cooldown = cooldown

    def select_available(
        self, model_name: str, *, now: datetime
    ) -> DeploymentWithKey | None:
        deployments = self._repo.get_available_for_model(model_name)
        if not deployments:
            return None

        candidates: list[tuple[Deployment, ProviderKey | None]] = []
        for dep in deployments:
            if dep.provider_key_id is None:
                candidates.append((dep, None))
                continue
            key = self._repo.get_key(dep.provider_key_id)
            if key is None:
                continue
            if key.state is not KeyState.AVAILABLE:
                continue
            if self._is_quota_exhausted(key):
                continue
            candidates.append((dep, key))

        if not candidates:
            return None

        def _sort_key(
            pair: tuple[Deployment, ProviderKey | None],
        ) -> tuple[int, int]:
            dep, key = pair
            rpd = key.rpd_used if key is not None else 0
            return (-dep.weight, rpd)

        candidates.sort(key=_sort_key)
        dep, key = candidates[0]
        return DeploymentWithKey(deployment=dep, key=key)

    def mark_success(
        self, deployment_id: int, *, tokens: int, latency_ms: int, now: datetime
    ) -> None:
        dep, key = self._resolve_deployment_and_key(deployment_id)
        if key is not None:
            self._repo.update_key(
                key.id,
                consecutive_fails=0,
                last_outcome=HealthOutcome.SUCCESS.value,
                rpd_used=key.rpd_used + 1,
                daily_token_used=key.daily_token_used + tokens,
            )
        self._repo.insert_health(
            provider_key_id=key.id if key is not None else None,
            deployment_id=deployment_id,
            model_name=dep.model_name,
            outcome=HealthOutcome.SUCCESS,
            latency_ms=latency_ms,
            tokens=tokens,
            error_excerpt=None,
            time=now,
        )

    def mark_failure(
        self,
        deployment_id: int,
        outcome: HealthOutcome,
        *,
        now: datetime,
        error: str | None = None,
    ) -> None:
        dep, key = self._resolve_deployment_and_key(deployment_id)

        if key is not None:
            if outcome is HealthOutcome.AUTH_FAIL:
                self._repo.update_key(
                    key.id,
                    state=KeyState.DEAD.value,
                    last_outcome=outcome.value,
                    consecutive_fails=key.consecutive_fails + 1,
                )
            elif outcome in (HealthOutcome.QUOTA,) or outcome in _SOFT_FAILS:
                new_fails = key.consecutive_fails + 1
                if new_fails >= self._allowed_fails:
                    self._repo.update_key(
                        key.id,
                        state=KeyState.COOLING.value,
                        last_outcome=outcome.value,
                        consecutive_fails=new_fails,
                        cooling_until=(now + self._cooldown).replace(tzinfo=now.tzinfo),
                    )
                else:
                    self._repo.update_key(
                        key.id,
                        last_outcome=outcome.value,
                        consecutive_fails=new_fails,
                    )
            elif outcome is HealthOutcome.BAD_REQUEST:
                self._repo.update_key(
                    key.id,
                    last_outcome=outcome.value,
                )

        self._repo.insert_health(
            provider_key_id=key.id if key is not None else None,
            deployment_id=deployment_id,
            model_name=dep.model_name,
            outcome=outcome,
            latency_ms=None,
            tokens=None,
            error_excerpt=error,
            time=now,
        )

    def reconcile_states(self, *, now: datetime) -> int:
        total = 0
        total += self._repo.expire_cooling(now)
        total += self._repo.expire_exhausted(now)
        return total

    def _is_quota_exhausted(self, key: ProviderKey) -> bool:
        if key.rpd_limit is not None and key.rpd_used >= key.rpd_limit:
            return True
        if (
            key.daily_token_limit is not None
            and key.daily_token_used >= key.daily_token_limit
        ):
            return True
        return False

    def _resolve_deployment_and_key(
        self, deployment_id: int
    ) -> tuple[Deployment, ProviderKey | None]:
        dep = self._repo.get_deployment(deployment_id)
        if dep is None:
            msg = f"Deployment {deployment_id} not found"
            raise ValueError(msg)
        if dep.provider_key_id is None:
            return dep, None
        key = self._repo.get_key(dep.provider_key_id)
        if key is None:
            msg = f"Key {dep.provider_key_id} not found for deployment {deployment_id}"
            raise ValueError(msg)
        return dep, key
