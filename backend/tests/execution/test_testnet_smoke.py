"""Gated pytest wrapper for S-EXEC-4 testnet smoke.

Skip:
    Missing ``CLAY_BINANCE_TESTNET_API_KEY`` / ``CLAY_BINANCE_TESTNET_API_SECRET``.
    Mark with ``-m slow`` or force with ``PYTEST_RUN_SMOKE=1``.
"""

import os

import pytest

from scripts.smoke_testnet_execution import run_smoke


@pytest.mark.slow
def test_testnet_execution_smoke() -> None:
    if not os.environ.get("CLAY_BINANCE_TESTNET_API_KEY") or not os.environ.get(
        "CLAY_BINANCE_TESTNET_API_SECRET"
    ):
        pytest.skip("testnet credentials are not configured")

    evidence = run_smoke()
    assert evidence.error is None, f"smoke failed: {evidence.error}"
    assert evidence.place_result is not None
    assert evidence.place_result.status == "open"
    assert len(evidence.open_orders_before_cancel) >= 1
    assert evidence.cancel_result is not None
    assert len(evidence.open_orders_after_cancel) == 0
