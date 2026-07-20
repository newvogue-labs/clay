"""Integration test: halt-latch mode probe late-bind wiring in bootstrap.

Verifies that ``build_services`` wires ``set_session_mode_probe`` into
``ExecutionProofGate`` exactly when all three conditions hold:
  1. ``CLAY_EXECUTION_MODE=testnet`` + non-empty API key/secret
     (→ ``execution_client`` is built)
  2. ``CLAY_PROOF_ENFORCE_SESSION=1``
  3. ``CLAY_PROOF_ENFORCE_HALT_LATCH=1``

Default OFF → probe not bound → ``_session_mode_probe is None`` →
live path byte-identical.
"""

from __future__ import annotations

import pytest

from ._helpers import build_services_for_integration

_BASE_ENV: dict[str, str] = {
    "CLAY_EXECUTION_MODE": "testnet",
    "CLAY_BINANCE_TESTNET_API_KEY": "test-key",
    "CLAY_BINANCE_TESTNET_API_SECRET": "test-secret",
    "CLAY_PROOF_ENFORCE_SESSION": "1",
    "CLAY_PROOF_ENFORCE_HALT_LATCH": "1",
}


def _set_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for key, val in env.items():
        monkeypatch.setenv(key, val)


class TestBootstrapHaltLatchWiring:
    """Real bootstrap wiring — no mocks, production build_services."""

    def test_both_flags_on_probe_bound(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_env(monkeypatch, _BASE_ENV)
        services = build_services_for_integration(tmp_path)  # type: ignore[arg-type]
        ec = services["execution_client"]
        assert ec is not None
        assert ec._session_mode_probe is not None  # noqa: SLF001

    def test_enforce_session_off_probe_none(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = {**_BASE_ENV, "CLAY_PROOF_ENFORCE_SESSION": "0"}
        _set_env(monkeypatch, env)
        services = build_services_for_integration(tmp_path)  # type: ignore[arg-type]
        ec = services["execution_client"]
        assert ec is not None
        assert ec._session_mode_probe is None  # noqa: SLF001

    def test_enforce_halt_latch_off_probe_none(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = {**_BASE_ENV, "CLAY_PROOF_ENFORCE_HALT_LATCH": "0"}
        _set_env(monkeypatch, env)
        services = build_services_for_integration(tmp_path)  # type: ignore[arg-type]
        ec = services["execution_client"]
        assert ec is not None
        assert ec._session_mode_probe is None  # noqa: SLF001

    def test_no_keys_client_none(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_env(
            monkeypatch,
            {
                "CLAY_EXECUTION_MODE": "testnet",
                "CLAY_PROOF_ENFORCE_SESSION": "1",
                "CLAY_PROOF_ENFORCE_HALT_LATCH": "1",
            },
        )
        monkeypatch.delenv("CLAY_BINANCE_TESTNET_API_KEY", raising=False)
        monkeypatch.delenv("CLAY_BINANCE_TESTNET_API_SECRET", raising=False)
        services = build_services_for_integration(tmp_path)  # type: ignore[arg-type]
        assert services["execution_client"] is None
