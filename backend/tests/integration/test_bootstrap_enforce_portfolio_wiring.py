"""Integration test: enforce-portfolio wiring in bootstrap.

Verifies that ``build_services`` passes ``proof_enforce_portfolio``
to ``ExecutionProofGate`` so that ``_enforce_portfolio`` matches the
config value.  Double-off contract: unset → False → gate dormant.
"""

from __future__ import annotations

import pytest

from ._helpers import build_services_for_integration

_BASE_ENV: dict[str, str] = {
    "CLAY_EXECUTION_MODE": "testnet",
    "CLAY_BINANCE_TESTNET_API_KEY": "test-key",
    "CLAY_BINANCE_TESTNET_API_SECRET": "test-secret",
}


def _set_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for key, val in env.items():
        monkeypatch.setenv(key, val)


class TestBootstrapEnforcePortfolioWiring:
    """Real bootstrap wiring — production build_services."""

    def test_flag_on_portfolio_enforced(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = {**_BASE_ENV, "CLAY_PROOF_ENFORCE_PORTFOLIO": "1"}
        _set_env(monkeypatch, env)
        services = build_services_for_integration(tmp_path)  # type: ignore[arg-type]
        ec = services["execution_client"]
        assert ec is not None
        assert ec._enforce_portfolio is True  # noqa: SLF001

    def test_flag_off_portfolio_dormant(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_env(monkeypatch, _BASE_ENV)
        services = build_services_for_integration(tmp_path)  # type: ignore[arg-type]
        ec = services["execution_client"]
        assert ec is not None
        assert ec._enforce_portfolio is False  # noqa: SLF001

    def test_unset_flag_portfolio_dormant(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_env(monkeypatch, _BASE_ENV)
        monkeypatch.delenv("CLAY_PROOF_ENFORCE_PORTFOLIO", raising=False)
        services = build_services_for_integration(tmp_path)  # type: ignore[arg-type]
        ec = services["execution_client"]
        assert ec is not None
        assert ec._enforce_portfolio is False  # noqa: SLF001
