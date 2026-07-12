"""Tests for OverrideService degraded-probe killswitch (S-LIVE-3).

Scope: _is_degraded() behavior with/without probe, fail-closed semantics.
No DB / no wiring — pure unit tests on OverrideService.
"""

from clay.execution.config import ExecutionConfig
from clay.execution.service import OverrideService


def _live_config() -> ExecutionConfig:
    return ExecutionConfig(mode="live", allow_live_override=True)


def _make_svc(**kwargs) -> OverrideService:
    return OverrideService(execution_config=_live_config(), **kwargs)


# ── probe=None (backward-compat) ──────────────────────────────────────


def test_degraded_probe_none_returns_false() -> None:
    svc = _make_svc()
    assert svc._is_degraded() is False
    assert svc.is_degraded() is False


# ── probe=True → degraded ─────────────────────────────────────────────


def test_degraded_probe_true_blocks_live_eligible() -> None:
    svc = _make_svc(degraded_probe=lambda: True)
    # Force confirmed state
    import asyncio

    asyncio.run(svc.request_override(actor="test"))
    asyncio.run(svc.confirm_override(actor="test"))
    assert svc.is_degraded() is True
    assert svc.is_live_eligible() is False


# ── probe=False → not degraded ────────────────────────────────────────


def test_degraded_probe_false_allows_live_eligible() -> None:
    svc = _make_svc(degraded_probe=lambda: False)
    import asyncio

    asyncio.run(svc.request_override(actor="test"))
    asyncio.run(svc.confirm_override(actor="test"))
    assert svc.is_degraded() is False
    assert svc.is_live_eligible() is True


# ── probe raises → fail-closed ────────────────────────────────────────


def test_degraded_probe_exception_fails_closed() -> None:
    def _explode() -> bool:
        raise RuntimeError("reliability unavailable")

    svc = _make_svc(degraded_probe=_explode)
    assert svc._is_degraded() is True
    assert svc.is_degraded() is True
    # Even with confirmed live config → not eligible
    import asyncio

    asyncio.run(svc.request_override(actor="test"))
    asyncio.run(svc.confirm_override(actor="test"))
    assert svc.is_live_eligible() is False


# ── set_degraded_probe (late binding) ─────────────────────────────────


def test_set_degraded_probe_late_binding() -> None:
    svc = _make_svc()
    assert svc._is_degraded() is False
    svc.set_degraded_probe(lambda: True)
    assert svc._is_degraded() is True
    assert svc.is_degraded() is True


# ── wiring smoke: state toggle follows probe ──────────────────────────


def test_probe_toggle_reflects_in_is_degraded() -> None:
    toggle = False
    svc = _make_svc(degraded_probe=lambda: toggle)
    assert svc.is_degraded() is False
    toggle = True
    assert svc.is_degraded() is True
    toggle = False
    assert svc.is_degraded() is False
