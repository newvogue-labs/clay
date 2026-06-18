"""Idempotent seed for ops.provider* tables (S3a).

Upserts the 4 providers / 3 keys / 7 deployments from the live
config.yaml so ConcreteProviderPoolRepository can query them.

⛔ Pre-flight: rejects any DB that is NOT the podman container
(TimescaleDB 2.27.1). Live 5432 has 2.6.3 — abort.
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
        "name": "ollama-local",
        "route_class": "local",
        "base_url": "http://127.0.0.1:11434",
        "trust": "local",
        "egress": "demo_only",
    },
    {
        "name": "google-aistudio",
        "route_class": "upstream",
        "base_url": None,
        "trust": "us",
        "egress": "demo_only",
    },
    {
        "name": "nvidia-nim",
        "route_class": "upstream",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "trust": "us",
        "egress": "demo_only",
    },
    {
        "name": "kimchi",
        "route_class": "upstream",
        "base_url": "https://llm.kimchi.dev/openai/v1",
        "trust": "us",
        "egress": "demo_only",
    },
]

KEYS = [
    {"provider_name": "google-aistudio", "account_label": "google-aistudio-1", "key_ref": "GEMINI_API_KEY"},
    {"provider_name": "nvidia-nim", "account_label": "nvidia-1", "key_ref": "NVIDIA_API_KEY"},
    {"provider_name": "kimchi", "account_label": "kimchi-1", "key_ref": "KIMCHI_API_KEY"},
]

DEPLOYMENTS = [
    {"model_name": "gemma4-e2b", "provider_name": "ollama-local", "key_ref": None, "upstream_model": "ollama/gemma4:e2b-it-qat", "params": {}},
    {"model_name": "local-ollama", "provider_name": "ollama-local", "key_ref": None, "upstream_model": "ollama/deepseek-v4-flash:cloud", "params": {}},
    {"model_name": "gemini-2.5-flash", "provider_name": "google-aistudio", "key_ref": "GEMINI_API_KEY", "upstream_model": "gemini/gemini-2.5-flash", "params": {}},
    {"model_name": "gemini-3.1-flash-lite", "provider_name": "google-aistudio", "key_ref": "GEMINI_API_KEY", "upstream_model": "gemini/gemini-3.1-flash-lite", "params": {}},
    {"model_name": "gemma-4-31b", "provider_name": "google-aistudio", "key_ref": "GEMINI_API_KEY", "upstream_model": "gemini/gemma-4-31b-it", "params": {}},
    {"model_name": "minimax-m3", "provider_name": "nvidia-nim", "key_ref": "NVIDIA_API_KEY", "upstream_model": "openai/minimaxai/minimax-m3", "params": {"rpm": 40}},
    {"model_name": "minimax-m2.7", "provider_name": "kimchi", "key_ref": "KIMCHI_API_KEY", "upstream_model": "openai/minimax-m2.7", "params": {}},
]

_TOKEN_ROUTER_MODELS = {"minimax-m3-via-tokenrouter"}


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
            f"expected {EXPECTED_TS_VERSION} (container). "
            "Refusing to seed — this looks like live 5432. Abort."
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
            {"name": p["name"], "route_class": p["route_class"], "base_url": p["base_url"],
             "trust": p["trust"], "egress": p["egress"], "now": now},
        ).one()
        ids[p["name"]] = int(row[0])
    return ids


def _upsert_keys(session: Session, provider_ids: dict[str, int]) -> dict[tuple[str, str], int]:
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
            {"provider_id": provider_ids[k["provider_name"]],
             "account_label": k["account_label"],
             "key_ref": k["key_ref"],
             "now": now},
        ).one()
        ids[(k["provider_name"], k["key_ref"])] = int(row[0])
    return ids


def _key_id_for_deployment(
    dep: dict,
    provider_ids: dict[str, int],
    key_ids: dict[tuple[str, str], int],
) -> int | None:
    if dep["key_ref"] is None:
        return None
    return key_ids.get((dep["provider_name"], dep["key_ref"]))


def _upsert_deployments(session: Session, provider_ids: dict[str, int], key_ids: dict[tuple[str, str], int]) -> None:
    now = datetime.now(UTC)
    for dep in DEPLOYMENTS:
        key_id = _key_id_for_deployment(dep, provider_ids, key_ids)
        provider_id = provider_ids[dep["provider_name"]]
        existing = session.execute(
            text("SELECT id FROM ops.provider_deployment WHERE model_name = :m"),
            {"m": dep["model_name"]},
        ).one_or_none()
        if existing is not None:
            session.execute(
                text("""
                    UPDATE ops.provider_deployment
                    SET provider_key_id = :provider_key_id,
                        provider_id = :provider_id,
                        upstream_model = :upstream_model,
                        params = :params,
                        updated_at = :now
                    WHERE id = :id
                """),
                {"provider_key_id": key_id, "provider_id": provider_id,
                 "upstream_model": dep["upstream_model"],
                 "params": _json_param(dep["params"]), "now": now, "id": int(existing[0])},
            )
        else:
            session.execute(
                text("""
                    INSERT INTO ops.provider_deployment
                        (model_name, provider_key_id, provider_id, upstream_model, params, created_at, updated_at)
                    VALUES (:model_name, :provider_key_id, :provider_id, :upstream_model, :params, :now, :now)
                """),
                {"model_name": dep["model_name"], "provider_key_id": key_id,
                 "provider_id": provider_id,
                 "upstream_model": dep["upstream_model"],
                 "params": _json_param(dep["params"]), "now": now},
            )
    session.flush()


def _json_param(params: dict) -> str:
    import json
    return json.dumps(params, sort_keys=True, default=str)


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

    count_providers = len(PROVIDERS)
    count_keys = len(KEYS)
    count_deployments = len(DEPLOYMENTS)
    print(f"Seeded {count_providers} providers, {count_keys} keys, {count_deployments} deployments.")
    print("TokenRouter deployments intentionally excluded (commented out in config).")


if __name__ == "__main__":
    main()
