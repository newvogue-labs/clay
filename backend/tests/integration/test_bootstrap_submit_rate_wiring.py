"""Integration test: submit-rate probe late-bind wiring in bootstrap.

Verifies that ``build_services`` wires ``set_session_submit_rate_probe``
into ``ExecutionProofGate`` exactly when all four conditions hold:
  1. ``CLAY_EXECUTION_MODE=testnet`` + non-empty API key/secret
     (→ ``execution_client`` is built)
  2. ``CLAY_PROOF_ENFORCE_SESSION=1``
  3. ``CLAY_PROOF_SUBMIT_RATE_MAX > 0``
  4. ``CLAY_PROOF_SUBMIT_RATE_WINDOW_SECONDS > 0``

Replaces the tautological ``TestBootstrapSubmitRateWiring`` unit tests
(D-11 follow-up) with real graph assertions against the production factory.
"""

from __future__ import annotations

import pytest

from ._helpers import build_services_for_integration

_BASE_ENV: dict[str, str] = {
    "CLAY_EXECUTION_MODE": "testnet",
    "CLAY_BINANCE_TESTNET_API_KEY": "test-key",
    "CLAY_BINANCE_TESTNET_API_SECRET": "test-secret",
    "CLAY_PROOF_ENFORCE_SESSION": "1",
    "CLAY_PROOF_SUBMIT_RATE_MAX": "5",
    "CLAY_PROOF_SUBMIT_RATE_WINDOW_SECONDS": "60",
}


def _set_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for key, val in env.items():
        monkeypatch.setenv(key, val)


class TestBootstrapSubmitRateWiring:
    """Real bootstrap wiring — no mocks, production build_services."""

    def test_all_conditions_probe_bound(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_env(monkeypatch, _BASE_ENV)
        services = build_services_for_integration(tmp_path)  # type: ignore[arg-type]
        ec = services["execution_client"]
        assert ec is not None
        assert ec._session_submit_rate_probe is not None  # noqa: SLF001

    def test_enforce_session_off_probe_none(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = {**_BASE_ENV, "CLAY_PROOF_ENFORCE_SESSION": "0"}
        _set_env(monkeypatch, env)
        services = build_services_for_integration(tmp_path)  # type: ignore[arg-type]
        ec = services["execution_client"]
        assert ec is not None
        assert ec._session_submit_rate_probe is None  # noqa: SLF001

    def test_max_zero_probe_none(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = {**_BASE_ENV, "CLAY_PROOF_SUBMIT_RATE_MAX": "0"}
        _set_env(monkeypatch, env)
        services = build_services_for_integration(tmp_path)  # type: ignore[arg-type]
        ec = services["execution_client"]
        assert ec is not None
        assert ec._session_submit_rate_probe is None  # noqa: SLF001

    def test_window_zero_probe_none(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = {**_BASE_ENV, "CLAY_PROOF_SUBMIT_RATE_WINDOW_SECONDS": "0"}
        _set_env(monkeypatch, env)
        services = build_services_for_integration(tmp_path)  # type: ignore[arg-type]
        ec = services["execution_client"]
        assert ec is not None
        assert ec._session_submit_rate_probe is None  # noqa: SLF001
