#!/usr/bin/env python3
"""Read-only reconciliation: render proposed config from DB, validate,
write to shadow path, and print diff report.

The live config is read-only — this script never touches the active
LiteLLM config. Writing to live + reload is S3c-2.

Guard: ``CLAY_PROVIDER_POOL_RECONCILE_ENABLED`` must be set to ``true``.
"""

from __future__ import annotations

import os
from pathlib import Path

from clay.ai_control.config_reconciler import ConfigReconciler, ConfigWriter
from clay.ai_control.provider_pool_repository import SqlProviderPoolRepository
from clay.db.session import build_session_factory

_CONFIG_PATH = Path(os.environ.get(
    "CLAY_LITELLM_CONFIG",
    "/home/emma/.config/clay/litellm/config.yaml",
))
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
        raise SystemExit("ERROR: TimescaleDB not found — not a TSDB database. Abort.")
    if str(row[0]) != _EXPECTED_TS:
        raise SystemExit(
            f"ERROR: TimescaleDB version {row[0]} != {_EXPECTED_TS} (container). "
            "Refusing — this looks like live 5432. Abort."
        )


def main() -> None:
    _check_flag()

    session_factory = build_session_factory()
    _check_preflight(session_factory)

    with session_factory() as session:
        repo = SqlProviderPoolRepository(session)
        rows = list(repo.list_enabled_deployments())

    reconciler = ConfigReconciler(_CONFIG_PATH)
    proposed = reconciler.render(rows)
    writer = ConfigWriter(reconciler)

    if writer.noop_skip(proposed):
        report = reconciler.diff(proposed.yaml)
        print("=== No-op: proposed config matches current ===")
        print(f"Shadow: {writer._default_shadow_path()}")
        print(f"Equivalent: {report.is_equivalent}")
        return

    shadow_path = writer.write_shadow(proposed)
    report = reconciler.diff(proposed.yaml)

    print(f"=== Shadow written: {shadow_path} ===")
    print(f"Size: {shadow_path.stat().st_size} bytes")
    print(f"Mode: {oct(shadow_path.stat().st_mode & 0o777)}")
    print()
    print("=== Diff (proposed vs live) ===")
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
