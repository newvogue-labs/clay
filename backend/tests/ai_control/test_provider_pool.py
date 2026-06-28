"""Unit tests for ProviderPool (S2).

Covers all FSM transitions from ADR-013-addendum,
select_available logic, and reconcile_states.
Deterministic via injected ``now``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from clay.ai_control.provider_pool import (
    Deployment,
    HealthOutcome,
    KeyState,
    ProviderKey,
    ProviderPool,
)


_EPOCH = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)


def _key(
    *,
    id: int = 1,
    state: KeyState = KeyState.AVAILABLE,
    fails: int = 0,
    last_outcome: HealthOutcome | None = None,
    cooling_until: datetime | None = None,
    reset_at: datetime | None = None,
    rpd_used: int = 0,
    daily_token_used: int = 0,
    rpd_limit: int | None = None,
    daily_token_limit: int | None = None,
) -> ProviderKey:
    return ProviderKey(
        id=id,
        provider_id=1,
        account_label=f"key-{id}",
        key_ref=f"KEY_{id}",
        state=state,
        consecutive_fails=fails,
        last_outcome=last_outcome,
        cooling_until=cooling_until,
        reset_at=reset_at,
        reset_tz=None,
        rpm_limit=None,
        rpd_limit=rpd_limit,
        rpd_used=rpd_used,
        daily_token_limit=daily_token_limit,
        daily_token_used=daily_token_used,
    )


def _dep(
    *,
    id: int = 1,
    model: str = "test-model",
    key_id: int | None = 1,
    weight: int = 1,
    enabled: bool = True,
) -> Deployment:
    return Deployment(
        id=id,
        model_name=model,
        provider_key_id=key_id,
        upstream_model=f"upstream/{model}",
        params={},
        weight=weight,
        enabled=enabled,
    )


class FakeRepo:
    """In-memory fake for ProviderPoolRepository."""

    def __init__(self) -> None:
        self.keys: dict[int, ProviderKey] = {}
        self.deployments: dict[int, Deployment] = {}
        self.health_records: list[dict] = []

    def add(
        self, key: ProviderKey | None = None, dep: Deployment | None = None
    ) -> None:
        if key is not None:
            self.keys[key.id] = key
        if dep is not None:
            self.deployments[dep.id] = dep

    # --- Protocol ---

    def get_available_for_model(self, model_name: str) -> list[Deployment]:
        return [
            d
            for d in self.deployments.values()
            if d.model_name == model_name and d.enabled
        ]

    def get_deployment(self, deployment_id: int) -> Deployment | None:
        return self.deployments.get(deployment_id)

    def get_key(self, key_id: int | None) -> ProviderKey | None:
        if key_id is None:
            return None
        return self.keys.get(key_id)

    def update_key(self, key_id: int, **updates: object) -> None:
        k = self.keys[key_id]
        for attr, val in updates.items():
            setattr(k, attr, val)

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
        self.health_records.append(
            {
                "provider_key_id": provider_key_id,
                "deployment_id": deployment_id,
                "model_name": model_name,
                "outcome": outcome,
                "latency_ms": latency_ms,
                "tokens": tokens,
                "error_excerpt": error_excerpt,
                "time": time,
            }
        )

    def list_enabled_deployments(self) -> list:
        return []

    def expire_cooling(self, now: datetime) -> int:
        count = 0
        for k in self.keys.values():
            if (
                k.state == KeyState.COOLING
                and k.cooling_until is not None
                and k.cooling_until <= now
            ):
                k.state = KeyState.AVAILABLE
                k.cooling_until = None
                count += 1
        return count

    def expire_exhausted(self, now: datetime) -> int:
        count = 0
        for k in self.keys.values():
            if (
                k.state == KeyState.EXHAUSTED
                and k.reset_at is not None
                and k.reset_at <= now
            ):
                k.state = KeyState.AVAILABLE
                k.rpd_used = 0
                k.daily_token_used = 0
                count += 1
        return count


# =========================================================
# select_available
# =========================================================


def test_select_available_returns_highest_weight() -> None:
    repo = FakeRepo()
    k = _key(id=1)
    repo.add(key=k, dep=_dep(id=1, weight=1, key_id=1))
    repo.add(key=_key(id=2), dep=_dep(id=2, weight=5, key_id=2))
    pool = ProviderPool(repo)
    result = pool.select_available("test-model", now=_EPOCH)
    assert result is not None
    assert result.deployment.id == 2


def test_select_available_skips_non_available_state() -> None:
    repo = FakeRepo()
    repo.add(key=_key(id=1, state=KeyState.COOLING), dep=_dep(id=1, key_id=1))
    repo.add(key=_key(id=2), dep=_dep(id=2, key_id=2))
    pool = ProviderPool(repo)
    result = pool.select_available("test-model", now=_EPOCH)
    assert result is not None
    assert result.deployment.id == 2


def test_select_available_skips_rpd_exhausted() -> None:
    repo = FakeRepo()
    repo.add(key=_key(id=1, rpd_limit=10, rpd_used=10), dep=_dep(id=1, key_id=1))
    repo.add(key=_key(id=2), dep=_dep(id=2, key_id=2))
    pool = ProviderPool(repo)
    result = pool.select_available("test-model", now=_EPOCH)
    assert result is not None
    assert result.deployment.id == 2


def test_select_available_skips_daily_token_exhausted() -> None:
    repo = FakeRepo()
    repo.add(
        key=_key(id=1, daily_token_limit=1000, daily_token_used=1000),
        dep=_dep(id=1, key_id=1),
    )
    repo.add(key=_key(id=2), dep=_dep(id=2, key_id=2))
    pool = ProviderPool(repo)
    result = pool.select_available("test-model", now=_EPOCH)
    assert result is not None
    assert result.deployment.id == 2


def test_select_available_none_when_all_exhausted() -> None:
    repo = FakeRepo()
    repo.add(key=_key(id=1, rpd_limit=10, rpd_used=10), dep=_dep(id=1, key_id=1))
    pool = ProviderPool(repo)
    result = pool.select_available("test-model", now=_EPOCH)
    assert result is None


def test_select_available_none_when_no_deployments() -> None:
    pool = ProviderPool(FakeRepo())
    result = pool.select_available("nonexistent", now=_EPOCH)
    assert result is None


def test_select_available_uses_lru_among_same_weight() -> None:
    repo = FakeRepo()
    repo.add(key=_key(id=1, rpd_used=10), dep=_dep(id=1, weight=1, key_id=1))
    repo.add(key=_key(id=2, rpd_used=2), dep=_dep(id=2, weight=1, key_id=2))
    pool = ProviderPool(repo)
    result = pool.select_available("test-model", now=_EPOCH)
    assert result is not None
    assert result.deployment.id == 2  # lower rpd_used = LRU


# =========================================================
# mark_success
# =========================================================


def test_mark_success_resets_fails() -> None:
    repo = FakeRepo()
    k = _key(id=1, fails=3)
    repo.add(key=k, dep=_dep(id=10, key_id=1))
    pool = ProviderPool(repo)
    pool.mark_success(10, tokens=50, latency_ms=200, now=_EPOCH)
    assert k.consecutive_fails == 0
    assert k.last_outcome == HealthOutcome.SUCCESS
    assert k.rpd_used == 1
    assert k.daily_token_used == 50


def test_mark_success_writes_health_record() -> None:
    repo = FakeRepo()
    repo.add(key=_key(id=1), dep=_dep(id=10, key_id=1))
    pool = ProviderPool(repo)
    pool.mark_success(10, tokens=100, latency_ms=150, now=_EPOCH)
    assert len(repo.health_records) == 1
    record = repo.health_records[0]
    assert record["outcome"] == HealthOutcome.SUCCESS
    assert record["latency_ms"] == 150
    assert record["tokens"] == 100
    assert record["deployment_id"] == 10


# =========================================================
# mark_failure — FSM transitions
# =========================================================


class TestMarkFailure:
    """Each row of the FSM table from ADR-013-addendum."""

    def test_auth_fail_sets_dead(self) -> None:
        repo = FakeRepo()
        k = _key(id=1)
        repo.add(key=k, dep=_dep(id=10, key_id=1))
        pool = ProviderPool(repo)
        pool.mark_failure(10, HealthOutcome.AUTH_FAIL, now=_EPOCH)
        assert k.state == KeyState.DEAD
        assert k.last_outcome == HealthOutcome.AUTH_FAIL
        assert k.consecutive_fails == 1

    @pytest.mark.parametrize(
        "outcome",
        [
            HealthOutcome.QUOTA,
            HealthOutcome.TIMEOUT,
            HealthOutcome.UPSTREAM,
        ],
    )
    def test_soft_fail_below_threshold_increments_fails(
        self, outcome: HealthOutcome
    ) -> None:
        repo = FakeRepo()
        k = _key(id=1, fails=0)
        repo.add(key=k, dep=_dep(id=10, key_id=1))
        pool = ProviderPool(repo, allowed_fails=2)
        pool.mark_failure(10, outcome, now=_EPOCH)
        assert k.state == KeyState.AVAILABLE
        assert k.consecutive_fails == 1

    @pytest.mark.parametrize(
        "outcome",
        [
            HealthOutcome.QUOTA,
            HealthOutcome.TIMEOUT,
            HealthOutcome.UPSTREAM,
        ],
    )
    def test_soft_fail_at_threshold_triggers_cooling(
        self, outcome: HealthOutcome
    ) -> None:
        repo = FakeRepo()
        k = _key(id=1, fails=1)
        repo.add(key=k, dep=_dep(id=10, key_id=1))
        pool = ProviderPool(repo, allowed_fails=2, cooldown=timedelta(hours=6))
        pool.mark_failure(10, outcome, now=_EPOCH)
        assert k.state == KeyState.COOLING
        assert k.consecutive_fails == 2
        assert k.cooling_until is not None
        assert k.cooling_until == _EPOCH + timedelta(hours=6)

    def test_bad_request_does_not_penalize_key(self) -> None:
        repo = FakeRepo()
        k = _key(id=1, fails=0)
        repo.add(key=k, dep=_dep(id=10, key_id=1))
        pool = ProviderPool(repo)
        pool.mark_failure(10, HealthOutcome.BAD_REQUEST, now=_EPOCH)
        assert k.state == KeyState.AVAILABLE
        assert k.consecutive_fails == 0
        assert k.last_outcome == HealthOutcome.BAD_REQUEST

    def test_bad_request_still_logs_health(self) -> None:
        repo = FakeRepo()
        repo.add(key=_key(id=1), dep=_dep(id=10, key_id=1))
        pool = ProviderPool(repo)
        pool.mark_failure(10, HealthOutcome.BAD_REQUEST, now=_EPOCH, error="bad prompt")
        assert len(repo.health_records) == 1
        assert repo.health_records[0]["outcome"] == HealthOutcome.BAD_REQUEST
        assert repo.health_records[0]["error_excerpt"] == "bad prompt"

    def test_auth_fail_health_record(self) -> None:
        repo = FakeRepo()
        repo.add(key=_key(id=1), dep=_dep(id=10, key_id=1))
        pool = ProviderPool(repo)
        pool.mark_failure(10, HealthOutcome.AUTH_FAIL, now=_EPOCH)
        assert any(r["outcome"] == HealthOutcome.AUTH_FAIL for r in repo.health_records)


# =========================================================
# reconcile_states
# =========================================================


def test_reconcile_cooling_expiry() -> None:
    repo = FakeRepo()
    past = _EPOCH - timedelta(hours=1)
    k = _key(id=1, state=KeyState.COOLING, cooling_until=past)
    repo.add(key=k, dep=_dep(id=10, key_id=1))
    pool = ProviderPool(repo)
    n = pool.reconcile_states(now=_EPOCH)
    assert n == 1
    assert k.state == KeyState.AVAILABLE
    assert k.cooling_until is None


def test_reconcile_cooling_not_yet_expired() -> None:
    repo = FakeRepo()
    future = _EPOCH + timedelta(hours=1)
    k = _key(id=1, state=KeyState.COOLING, cooling_until=future)
    repo.add(key=k)
    pool = ProviderPool(repo)
    n = pool.reconcile_states(now=_EPOCH)
    assert n == 0
    assert k.state == KeyState.COOLING


def test_reconcile_exhausted_reset() -> None:
    repo = FakeRepo()
    past = _EPOCH - timedelta(hours=1)
    k = _key(
        id=1,
        state=KeyState.EXHAUSTED,
        reset_at=past,
        rpd_used=100,
        daily_token_used=5000,
    )
    repo.add(key=k, dep=_dep(id=10, key_id=1))
    pool = ProviderPool(repo)
    n = pool.reconcile_states(now=_EPOCH)
    assert n == 1
    assert k.state == KeyState.AVAILABLE
    assert k.rpd_used == 0
    assert k.daily_token_used == 0


def test_reconcile_exhausted_not_yet() -> None:
    repo = FakeRepo()
    future = _EPOCH + timedelta(hours=1)
    k = _key(id=1, state=KeyState.EXHAUSTED, reset_at=future)
    repo.add(key=k)
    pool = ProviderPool(repo)
    n = pool.reconcile_states(now=_EPOCH)
    assert n == 0
    assert k.state == KeyState.EXHAUSTED


def test_reconcile_both_transitions() -> None:
    repo = FakeRepo()
    past = _EPOCH - timedelta(hours=1)
    repo.add(key=_key(id=1, state=KeyState.COOLING, cooling_until=past))
    repo.add(
        key=_key(
            id=2,
            state=KeyState.EXHAUSTED,
            reset_at=past,
            rpd_used=50,
            daily_token_used=2000,
        )
    )
    pool = ProviderPool(repo)
    n = pool.reconcile_states(now=_EPOCH)
    assert n == 2


def test_reconcile_idempotent() -> None:
    repo = FakeRepo()
    past = _EPOCH - timedelta(hours=1)
    k = _key(id=1, state=KeyState.COOLING, cooling_until=past)
    repo.add(key=k, dep=_dep(id=10, key_id=1))
    pool = ProviderPool(repo)
    assert pool.reconcile_states(now=_EPOCH) == 1
    assert k.state == KeyState.AVAILABLE
    assert pool.reconcile_states(now=_EPOCH) == 0  # already available


# =========================================================
# Edge cases
# =========================================================


def test_missing_deployment_raises() -> None:
    pool = ProviderPool(FakeRepo())
    with pytest.raises(ValueError, match="Deployment 999 not found"):
        pool.mark_success(999, tokens=0, latency_ms=0, now=_EPOCH)


def test_missing_key_raises() -> None:
    repo = FakeRepo()
    repo.add(dep=_dep(id=10, key_id=999))  # no key with id=999
    pool = ProviderPool(repo)
    with pytest.raises(ValueError, match="Key 999 not found"):
        pool.mark_success(10, tokens=0, latency_ms=0, now=_EPOCH)


def test_select_available_skips_disabled_deployment() -> None:
    repo = FakeRepo()
    repo.add(key=_key(id=1), dep=_dep(id=1, enabled=False, key_id=1))
    repo.add(key=_key(id=2), dep=_dep(id=2, key_id=2))
    pool = ProviderPool(repo)
    result = pool.select_available("test-model", now=_EPOCH)
    assert result is not None
    assert result.deployment.id == 2


def test_select_available_keyless_local_deployment() -> None:
    repo = FakeRepo()
    repo.add(dep=_dep(id=1, key_id=None))  # local, no key
    repo.add(key=_key(id=1), dep=_dep(id=2, key_id=1))
    pool = ProviderPool(repo)
    result = pool.select_available("test-model", now=_EPOCH)
    assert result is not None
    assert result.deployment.id == 1  # local deployment selected


def test_mark_success_keyless_deployment_does_not_crash() -> None:
    repo = FakeRepo()
    repo.add(dep=_dep(id=10, key_id=None))  # local, no key
    pool = ProviderPool(repo)
    pool.mark_success(10, tokens=0, latency_ms=0, now=_EPOCH)
    assert len(repo.health_records) == 1


def test_mark_failure_keyless_deployment_does_not_crash() -> None:
    repo = FakeRepo()
    repo.add(dep=_dep(id=10, key_id=None))
    pool = ProviderPool(repo)
    pool.mark_failure(10, HealthOutcome.TIMEOUT, now=_EPOCH)
    assert len(repo.health_records) == 1
