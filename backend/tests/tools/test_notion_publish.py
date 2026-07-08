from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from clay.tools.notion_publish import (
    NotionKnowledgePublisher,
    NotionManifest,
    NotionManifestEntry,
    NotionPlanAction,
    NotionPublisherConfig,
)
from clay.knowledge.vault_core import VaultFile


SMA_CROSSOVER_FM = """\
---
title: SMA Crossover
kb_category: strategy_rule
priority: high
runtime_eligible: true
status: peer_reviewed
tags:
  - momentum
  - trend
domain: trading
---
Use SMA crossover on H1 for trend confirmation.
"""

ENTRY_RULE_FM = """\
---
title: Entry Rule
kb_category: checklist
priority: medium
runtime_eligible: true
status: peer_reviewed
tags:
  - entry
domain: trading
---
Check volume before entry.
"""

OBSERVATION_FM = """\
---
title: Market Observation
kb_category: observation
priority: low
runtime_eligible: true
status: live
tags:
  - btc
domain: trading
---
BTC is ranging.
"""


def make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    market_dir = vault / "market"
    market_dir.mkdir(parents=True)
    (market_dir / "sma-crossover.md").write_text(SMA_CROSSOVER_FM)
    strategy_dir = vault / "strategy"
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "entry-rule.md").write_text(ENTRY_RULE_FM)
    obs_dir = vault / "observation"
    obs_dir.mkdir(parents=True)
    (obs_dir / "market-note.md").write_text(OBSERVATION_FM)
    (vault / "index.md").write_text("# Index")
    (vault / "AGENTS.md").write_text("# Agent rules")
    return vault


def make_manifest(path: Path, entries: dict[str, dict]) -> NotionManifest:
    files = {
        k: NotionManifestEntry(
            id=v["id"], page_id=v.get("page_id"), content_hash=v["content_hash"]
        )
        for k, v in entries.items()
    }
    manifest = NotionManifest(version=1, files=files)
    manifest.save(path)
    return manifest


def hash_for(
    title: str, category: str, priority: str, tags: list[str], content: str
) -> str:
    tags_csv = ",".join(tags)
    payload = f"{title}|{category}|{priority}|{tags_csv}|{content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_vf(id: str, content_hash: str) -> VaultFile:
    return VaultFile(
        id=id,
        title="test",
        category="note",
        priority="medium",
        tags=[],
        content="",
        content_hash=content_hash,
        source_type=f"vault:{id}",
    )


class TestNotionManifestRoundTrip:
    def test_empty_manifest(self, tmp_path: Path) -> None:
        path = tmp_path / "notion-sync-manifest.json"
        with open(path, "w") as f:
            json.dump({"version": 1, "files": {}}, f)

        m = NotionManifest.load(path)
        assert m.version == 1
        assert m.files == {}

    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "notion-sync-manifest.json"
        original = NotionManifest(
            version=1,
            files={
                "market/sma-crossover": NotionManifestEntry(
                    id="market/sma-crossover",
                    page_id="abc123",
                    content_hash="hash1",
                ),
                "strategy/entry-rule": NotionManifestEntry(
                    id="strategy/entry-rule",
                    page_id=None,
                    content_hash="hash2",
                ),
            },
        )
        original.save(path)

        loaded = NotionManifest.load(path)
        assert loaded.version == original.version
        assert loaded.files["market/sma-crossover"].page_id == "abc123"
        assert loaded.files["strategy/entry-rule"].page_id is None
        assert loaded.files["market/sma-crossover"].content_hash == "hash1"
        assert loaded.files["strategy/entry-rule"].id == "strategy/entry-rule"

    def test_load_non_existent(self, tmp_path: Path) -> None:
        path = tmp_path / "not-synced" / "notion-sync-manifest.json"
        m = NotionManifest.load(path)
        assert m.version == 1
        assert m.files == {}


class TestNotionBuildPlan:
    def test_all_cases(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        config = NotionPublisherConfig(vault_path=vault)
        publisher = NotionKnowledgePublisher(config)

        entry_hash = hash_for(
            title="Entry Rule",
            category="checklist",
            priority="medium",
            tags=["entry", "trading"],
            content="Check volume before entry.",
        )
        make_manifest(
            publisher.manifest_path,
            {
                "market/sma-crossover": {
                    "id": "market/sma-crossover",
                    "page_id": "page-update",
                    "content_hash": "different_hash",
                },
                "strategy/entry-rule": {
                    "id": "strategy/entry-rule",
                    "page_id": "page-skip",
                    "content_hash": entry_hash,
                },
                "strategy/gone": {
                    "id": "strategy/gone",
                    "page_id": "page-delete",
                    "content_hash": "x" * 64,
                },
            },
        )
        publisher.manifest = NotionManifest.load(publisher.manifest_path)

        files = publisher.read_vault_files()
        plan = publisher.build_plan(files)

        assert len(plan) == 4
        by_id = {a.id: a for a in plan}

        assert by_id["market/sma-crossover"].action == "update"
        assert by_id["market/sma-crossover"].page_id == "page-update"

        assert by_id["strategy/entry-rule"].action == "skip"
        assert by_id["strategy/entry-rule"].page_id == "page-skip"

        assert by_id["strategy/gone"].action == "delete"
        assert by_id["strategy/gone"].page_id == "page-delete"

        assert by_id["observation/market-note"].action == "create"
        assert by_id["observation/market-note"].page_id is None
        assert by_id["observation/market-note"].file is not None

    def test_create_no_manifest(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        config = NotionPublisherConfig(vault_path=vault)
        publisher = NotionKnowledgePublisher(config)

        plan = publisher.build_plan()
        assert all(a.action in ("create", "skip") for a in plan)
        assert all(a.page_id is None for a in plan if a.action == "create")

    def test_delete_orphan(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        config = NotionPublisherConfig(vault_path=vault)
        publisher = NotionKnowledgePublisher(config)

        make_manifest(
            publisher.manifest_path,
            {
                "orphan/note": {
                    "id": "orphan/note",
                    "page_id": "page-orphan",
                    "content_hash": "x" * 64,
                },
            },
        )
        publisher.manifest = NotionManifest.load(publisher.manifest_path)

        plan = publisher.build_plan()
        orphans = [a for a in plan if a.action == "delete"]
        assert len(orphans) == 1
        assert orphans[0].page_id == "page-orphan"


class FakeNotionClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.next_page_id = 100

    async def create_page(self, database_id: str, file: VaultFile) -> str:
        pid = f"page-{self.next_page_id}"
        self.next_page_id += 1
        self.calls.append(f"create:{file.id}")
        return pid

    async def update_page(self, page_id: str, file: VaultFile) -> None:
        self.calls.append(f"update:{file.id}")

    async def archive_page(self, page_id: str) -> None:
        self.calls.append(f"archive:{page_id}")


class TestApply:
    @pytest.mark.asyncio
    async def test_create_saves_page_id_and_hash(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        config = NotionPublisherConfig(vault_path=vault)
        publisher = NotionKnowledgePublisher(config)
        plan = publisher.build_plan()
        creates = [a for a in plan if a.action == "create"]
        assert len(creates) == 3

        client = FakeNotionClient()
        await publisher.apply([creates[0]], client)

        assert client.calls == ["create:market/sma-crossover"]
        assert publisher.manifest.files["market/sma-crossover"].page_id == "page-100"
        assert publisher.manifest.files["market/sma-crossover"].content_hash != ""

    @pytest.mark.asyncio
    async def test_update_calls_client_and_refreshes_hash(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        config = NotionPublisherConfig(vault_path=vault)
        publisher = NotionKnowledgePublisher(config)

        sma_hash = hash_for(
            title="SMA Crossover",
            category="strategy_rule",
            priority="high",
            tags=["momentum", "trend", "trading"],
            content="Use SMA crossover on H1 for trend confirmation.",
        )
        make_manifest(
            publisher.manifest_path,
            {
                "market/sma-crossover": {
                    "id": "market/sma-crossover",
                    "page_id": "page-old",
                    "content_hash": "stale_hash",
                },
            },
        )
        publisher.manifest = NotionManifest.load(publisher.manifest_path)
        plan = publisher.build_plan()
        updates = [a for a in plan if a.action == "update"]
        assert len(updates) == 1

        client = FakeNotionClient()
        await publisher.apply(updates, client)

        assert client.calls == ["update:market/sma-crossover"]
        assert publisher.manifest.files["market/sma-crossover"].content_hash == sma_hash

    @pytest.mark.asyncio
    async def test_skip_does_not_call_client(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        config = NotionPublisherConfig(vault_path=vault)
        publisher = NotionKnowledgePublisher(config)

        strat_hash = hash_for(
            title="Entry Rule",
            category="checklist",
            priority="medium",
            tags=["entry", "trading"],
            content="Check volume before entry.",
        )
        make_manifest(
            publisher.manifest_path,
            {
                "strategy/entry-rule": {
                    "id": "strategy/entry-rule",
                    "page_id": "page-skip",
                    "content_hash": strat_hash,
                },
            },
        )
        publisher.manifest = NotionManifest.load(publisher.manifest_path)
        plan = publisher.build_plan()
        skips = [a for a in plan if a.action == "skip"]
        assert len(skips) >= 1

        client = FakeNotionClient()
        await publisher.apply([skips[0]], client)

        assert client.calls == []

    @pytest.mark.asyncio
    async def test_delete_deferred_manifest_unchanged(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        config = NotionPublisherConfig(vault_path=vault)
        publisher = NotionKnowledgePublisher(config)

        make_manifest(
            publisher.manifest_path,
            {
                "orphan/note": {
                    "id": "orphan/note",
                    "page_id": "page-orphan",
                    "content_hash": "x" * 64,
                },
            },
        )
        publisher.manifest = NotionManifest.load(publisher.manifest_path)
        plan = publisher.build_plan()
        deletes = [a for a in plan if a.action == "delete"]
        assert len(deletes) == 1

        client = FakeNotionClient()
        await publisher.apply(deletes, client)

        assert client.calls == []
        assert "orphan/note" in publisher.manifest.files

    @pytest.mark.asyncio
    async def test_crash_safe_manifest_saved_after_each_action(
        self, tmp_path: Path
    ) -> None:
        vault = make_vault(tmp_path)
        config = NotionPublisherConfig(vault_path=vault)
        publisher = NotionKnowledgePublisher(config)

        create = NotionPlanAction(
            action="create", id="test/crash", file=make_vf("test/crash", "h1")
        )
        create2 = NotionPlanAction(
            action="create", id="test/safe", file=make_vf("test/safe", "h2")
        )

        client = FakeNotionClient()
        with patch("clay.tools.notion_publish.NotionManifest.save") as mock_save:
            await publisher.apply([create, create2], client)

        assert mock_save.call_count == 2
