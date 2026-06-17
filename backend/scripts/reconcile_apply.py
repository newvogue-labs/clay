#!/usr/bin/env python3
"""One-shot apply: render proposed config from DB → validate → backup →
atomic write as clay → restart → health-check → auto-rollback.

Guard: ``CLAY_PROVIDER_POOL_RECONCILE_ENABLED=true``.
Use ``--force`` to bypass no-op skip (rehearsal mode).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from clay.ai_control.config_reconciler import (
    ConfigReconciler,
    ConfigWriter,
)
from clay.ai_control.provider_pool_repository import SqlProviderPoolRepository
from clay.db.session import build_session_factory

_CONFIG_PATH = Path("/etc/clay/litellm/config.yaml")
_EXPECTED_TS = "2.27.1"
_ENVVAR = "CLAY_PROVIDER_POOL_RECONCILE_ENABLED"
_FLAG_VALUE = "true"


def _check_flag() -> None:
    if os.environ.get(_ENVVAR, "").lower() != _FLAG_VALUE:
        msg = (
            f"{_ENVVAR} is not set to 'true' (got {os.environ.get(_ENVVAR)!r}). "
            "Refusing to run."
        )
        raise SystemExit(msg)


def _check_preflight(session_factory) -> None:
    with session_factory() as session:
        from sqlalchemy import text

        row = session.execute(
            text("SELECT extversion FROM pg_extension WHERE extname='timescaledb'"),
        ).one_or_none()
    if row is None:
        raise SystemExit("ERROR: TimescaleDB not found. Abort.")
    if str(row[0]) != _EXPECTED_TS:
        raise SystemExit(
            f"ERROR: TimescaleDB version {row[0]} != {_EXPECTED_TS} (container). "
            "Refusing — this looks like live 5432. Abort."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply rendered config to live LiteLLM")
    parser.add_argument("--force", action="store_true", help="Bypass no-op skip (rehearsal mode)")
    args = parser.parse_args()

    _check_flag()

    session_factory = build_session_factory()
    _check_preflight(session_factory)

    with session_factory() as session:
        repo = SqlProviderPoolRepository(session)
        rows = list(repo.list_enabled_deployments())

    reconciler = ConfigReconciler(_CONFIG_PATH)
    proposed = reconciler.render(rows)
    writer = ConfigWriter(reconciler)

    report = writer.apply_live(proposed, force=args.force)

    print("=== Apply Report ===")
    print(f"Applied:    {report.applied}")
    print(f"Backup:     {report.backup_path}")
    print(f"Restart OK: {report.restart_ok}")
    print(f"Health OK:  {report.health_ok}")
    print(f"Rolled back: {report.rolled_back}")
    if report.error:
        print(f"Error:      {report.error}")

    if report.error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
