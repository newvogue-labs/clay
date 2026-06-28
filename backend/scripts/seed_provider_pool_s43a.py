"""Idempotent S4-3a seed: add groq/cerebras/openrouter + keys + depls to 5433.

Pre-flight: TimescaleDB 2.27.1 (podman container).
ON CONFLICT everywhere — safe to re-run.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from clay.db.session import build_session_factory


EXPECTED_TS_VERSION = os.environ.get("EXPECTED_TS_VERSION", "2.27.1")

PROVIDERS = [
    {
        "name": "groq",
        "route_class": "upstream",
        "base_url": None,
        "trust": "us",
        "egress": "demo_only",
    },
    {
        "name": "cerebras",
        "route_class": "upstream",
        "base_url": None,
        "trust": "us",
        "egress": "demo_only",
    },
    {
        "name": "openrouter",
        "route_class": "upstream",
        "base_url": None,
        "trust": "us",
        "egress": "demo_only",
    },
]

KEYS = [
    {"provider_name": "groq", "account_label": "groq-1", "key_ref": "GROQ_API_KEY"},
    {"provider_name": "groq", "account_label": "groq-2", "key_ref": "GROQ_API_KEY_2"},
    {
        "provider_name": "cerebras",
        "account_label": "cerebras-1",
        "key_ref": "CEREBRAS_API_KEY",
    },
    {
        "provider_name": "cerebras",
        "account_label": "cerebras-2",
        "key_ref": "CEREBRAS_API_KEY_2",
    },
    {
        "provider_name": "openrouter",
        "account_label": "openrouter-1",
        "key_ref": "OPENROUTER_API_KEY",
    },
    {
        "provider_name": "openrouter",
        "account_label": "openrouter-2",
        "key_ref": "OPENROUTER_API_KEY_2",
    },
    {
        "provider_name": "openrouter",
        "account_label": "openrouter-3",
        "key_ref": "OPENROUTER_API_KEY_3",
    },
]

DEPLOYMENTS = [
    # llama-3.3-70b: groq (×2)
    {
        "model_name": "llama-3.3-70b",
        "provider_name": "groq",
        "account_label": "groq-1",
        "upstream_model": "groq/llama-3.3-70b-versatile",
    },
    {
        "model_name": "llama-3.3-70b",
        "provider_name": "groq",
        "account_label": "groq-2",
        "upstream_model": "groq/llama-3.3-70b-versatile",
    },
    # llama-3.3-70b: openrouter (×3)
    {
        "model_name": "llama-3.3-70b",
        "provider_name": "openrouter",
        "account_label": "openrouter-1",
        "upstream_model": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    },
    {
        "model_name": "llama-3.3-70b",
        "provider_name": "openrouter",
        "account_label": "openrouter-2",
        "upstream_model": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    },
    {
        "model_name": "llama-3.3-70b",
        "provider_name": "openrouter",
        "account_label": "openrouter-3",
        "upstream_model": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    },
    # gpt-oss-120b: groq (×2)
    {
        "model_name": "gpt-oss-120b",
        "provider_name": "groq",
        "account_label": "groq-1",
        "upstream_model": "groq/openai/gpt-oss-120b",
    },
    {
        "model_name": "gpt-oss-120b",
        "provider_name": "groq",
        "account_label": "groq-2",
        "upstream_model": "groq/openai/gpt-oss-120b",
    },
    # gpt-oss-120b: cerebras (×2)
    {
        "model_name": "gpt-oss-120b",
        "provider_name": "cerebras",
        "account_label": "cerebras-1",
        "upstream_model": "cerebras/gpt-oss-120b",
    },
    {
        "model_name": "gpt-oss-120b",
        "provider_name": "cerebras",
        "account_label": "cerebras-2",
        "upstream_model": "cerebras/gpt-oss-120b",
    },
    # gpt-oss-120b: openrouter (×3)
    {
        "model_name": "gpt-oss-120b",
        "provider_name": "openrouter",
        "account_label": "openrouter-1",
        "upstream_model": "openrouter/openai/gpt-oss-120b:free",
    },
    {
        "model_name": "gpt-oss-120b",
        "provider_name": "openrouter",
        "account_label": "openrouter-2",
        "upstream_model": "openrouter/openai/gpt-oss-120b:free",
    },
    {
        "model_name": "gpt-oss-120b",
        "provider_name": "openrouter",
        "account_label": "openrouter-3",
        "upstream_model": "openrouter/openai/gpt-oss-120b:free",
    },
    # gpt-oss-20b: groq (×2)
    {
        "model_name": "gpt-oss-20b",
        "provider_name": "groq",
        "account_label": "groq-1",
        "upstream_model": "groq/openai/gpt-oss-20b",
    },
    {
        "model_name": "gpt-oss-20b",
        "provider_name": "groq",
        "account_label": "groq-2",
        "upstream_model": "groq/openai/gpt-oss-20b",
    },
    # gpt-oss-20b: openrouter (×3)
    {
        "model_name": "gpt-oss-20b",
        "provider_name": "openrouter",
        "account_label": "openrouter-1",
        "upstream_model": "openrouter/openai/gpt-oss-20b:free",
    },
    {
        "model_name": "gpt-oss-20b",
        "provider_name": "openrouter",
        "account_label": "openrouter-2",
        "upstream_model": "openrouter/openai/gpt-oss-20b:free",
    },
    {
        "model_name": "gpt-oss-20b",
        "provider_name": "openrouter",
        "account_label": "openrouter-3",
        "upstream_model": "openrouter/openai/gpt-oss-20b:free",
    },
    # gemma-4-31b: openrouter (×3)
    {
        "model_name": "gemma-4-31b",
        "provider_name": "openrouter",
        "account_label": "openrouter-1",
        "upstream_model": "openrouter/google/gemma-4-31b-it:free",
    },
    {
        "model_name": "gemma-4-31b",
        "provider_name": "openrouter",
        "account_label": "openrouter-2",
        "upstream_model": "openrouter/google/gemma-4-31b-it:free",
    },
    {
        "model_name": "gemma-4-31b",
        "provider_name": "openrouter",
        "account_label": "openrouter-3",
        "upstream_model": "openrouter/google/gemma-4-31b-it:free",
    },
]


def _check_preflight(session: Session) -> None:
    row = session.execute(
        text("SELECT extversion FROM pg_extension WHERE extname='timescaledb'"),
    ).one_or_none()
    if row is None:
        msg = "TimescaleDB extension not found — not a TSDB database. Abort."
        raise SystemExit(msg)
    version = str(row[0])
    if version != EXPECTED_TS_VERSION:
        msg = (
            f"TimescaleDB version mismatch: got {version}, "
            f"expected {EXPECTED_TS_VERSION} (podman). "
            "Refusing to seed — this looks like a different DB. Abort."
        )
        raise SystemExit(msg)


def _upsert_providers(session: Session) -> dict[str, int]:
    now = datetime.now(UTC)
    ids: dict[str, int] = {}
    for p in PROVIDERS:
        row = session.execute(
            text("""
                INSERT INTO ops.provider (name, route_class, base_url, trust, egress, created_at, updated_at)
                VALUES (:name, :route_class, :base_url, :trust, :egress, :now, :now)
                ON CONFLICT (name) DO UPDATE SET
                    route_class = EXCLUDED.route_class,
                    base_url = EXCLUDED.base_url,
                    trust = EXCLUDED.trust,
                    egress = EXCLUDED.egress,
                    updated_at = EXCLUDED.updated_at
                RETURNING id
            """),
            {
                "name": p["name"],
                "route_class": p["route_class"],
                "base_url": p["base_url"],
                "trust": p["trust"],
                "egress": p["egress"],
                "now": now,
            },
        ).one()
        ids[p["name"]] = int(row[0])
    return ids


def _upsert_keys(
    session: Session, provider_ids: dict[str, int]
) -> dict[tuple[str, str], int]:
    now = datetime.now(UTC)
    ids: dict[tuple[str, str], int] = {}
    for k in KEYS:
        row = session.execute(
            text("""
                INSERT INTO ops.provider_key (provider_id, account_label, key_ref, created_at, updated_at)
                VALUES (:provider_id, :account_label, :key_ref, :now, :now)
                ON CONFLICT (provider_id, account_label) DO UPDATE SET
                    key_ref = EXCLUDED.key_ref,
                    updated_at = EXCLUDED.updated_at
                RETURNING id
            """),
            {
                "provider_id": provider_ids[k["provider_name"]],
                "account_label": k["account_label"],
                "key_ref": k["key_ref"],
                "now": now,
            },
        ).one()
        ids[(k["provider_name"], k["account_label"])] = int(row[0])
    return ids


def _upsert_deployments(
    session: Session,
    provider_ids: dict[str, int],
    key_ids: dict[tuple[str, str], int],
) -> None:
    now = datetime.now(UTC)
    for dep in DEPLOYMENTS:
        provider_id = provider_ids[dep["provider_name"]]
        key_id = key_ids.get((dep["provider_name"], dep["account_label"]))
        existing = session.execute(
            text("""
                SELECT id FROM ops.provider_deployment
                WHERE model_name = :m AND provider_key_id = :pk AND upstream_model = :up
            """),
            {"m": dep["model_name"], "pk": key_id, "up": dep["upstream_model"]},
        ).one_or_none()
        if existing is not None:
            session.execute(
                text("""
                    UPDATE ops.provider_deployment
                    SET provider_key_id = :provider_key_id,
                        provider_id = :provider_id,
                        upstream_model = :upstream_model,
                        updated_at = :now
                    WHERE id = :id
                """),
                {
                    "provider_key_id": key_id,
                    "provider_id": provider_id,
                    "upstream_model": dep["upstream_model"],
                    "now": now,
                    "id": int(existing[0]),
                },
            )
        else:
            session.execute(
                text("""
                    INSERT INTO ops.provider_deployment
                        (model_name, provider_key_id, provider_id, upstream_model, created_at, updated_at)
                    VALUES (:model_name, :provider_key_id, :provider_id, :upstream_model, :now, :now)
                    ON CONFLICT (model_name, provider_key_id, upstream_model) DO NOTHING
                """),
                {
                    "model_name": dep["model_name"],
                    "provider_key_id": key_id,
                    "provider_id": provider_id,
                    "upstream_model": dep["upstream_model"],
                    "now": now,
                },
            )
    session.flush()


def main() -> None:
    probe_factory = build_session_factory()
    with probe_factory() as probe_session:
        _check_preflight(probe_session)

    session_factory = build_session_factory()
    with session_factory() as session:
        provider_ids = _upsert_providers(session)
        key_ids = _upsert_keys(session, provider_ids)
        _upsert_deployments(session, provider_ids, key_ids)
        session.commit()

    print(
        f"S4-3a seeded: {len(PROVIDERS)} providers, "
        f"{len(KEYS)} keys, {len(DEPLOYMENTS)} deployments."
    )


if __name__ == "__main__":
    main()
