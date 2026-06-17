#!/usr/bin/env python3
"""Read-only parity check: render proposed config from DB and diff against live.

Usage:
    uv run python scripts/parity_check_config.py

Pre-flight:
    - Checks TimescaleDB extversion = 2.27.1 (container guard)
    - Opens /etc/clay/litellm/config.yaml for reading ONLY

Output:
    - Prints ParityReport with added/removed/changed lists
    - Prints the proposed YAML (stdout, dry-run)
"""

from __future__ import annotations

from pathlib import Path

from clay.ai_control.config_reconciler import ConfigReconciler
from clay.ai_control.provider_pool_repository import SqlProviderPoolRepository
from clay.db.session import build_session_factory

_CONFIG_PATH = Path("/etc/clay/litellm/config.yaml")
_EXPECTED_TS = "2.27.1"


def _check_preflight(session_factory) -> None:
    with session_factory() as session:
        from sqlalchemy import text

        row = session.execute(
            text("SELECT extversion FROM pg_extension WHERE extname='timescaledb'"),
        ).one_or_none()
    if row is None:
        raise SystemExit("ERROR: TimescaleDB not found — not a TSDB database. Abort.")
    if str(row[0]) != _EXPECTED_TS:
        raise SystemExit(
            f"ERROR: TimescaleDB version {row[0]} != {_EXPECTED_TS} (container). "
            "Refusing — this looks like live 5432. Abort."
        )


def main() -> None:
    session_factory = build_session_factory()
    _check_preflight(session_factory)

    with session_factory() as session:
        repo = SqlProviderPoolRepository(session)
        rows = repo.list_enabled_deployments()

    reconciler = ConfigReconciler(_CONFIG_PATH)
    proposed = reconciler.render(rows)
    report = reconciler.diff(proposed.yaml)

    print("=== Parity Report ===")
    print(f"Equivalent: {report.is_equivalent}")
    if report.added:
        print(f"\nAdded ({len(report.added)}):")
        for mn, um in report.added:
            print(f"  + {mn} → {um}")
    if report.removed:
        print(f"\nRemoved ({len(report.removed)}):")
        for mn, um in report.removed:
            print(f"  - {mn} → {um}")
    if report.changed:
        print(f"\nChanged ({len(report.changed)}):")
        for mn, um, old, new in report.changed:
            print(f"  ~ {mn} → {um}")
            print(f"    old: {old}")
            print(f"    new: {new}")

    print(f"\n=== Proposed config ({len(rows)} deployments) ===")
    print(proposed.yaml)


if __name__ == "__main__":
    main()
