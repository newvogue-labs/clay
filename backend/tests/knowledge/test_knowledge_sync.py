from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clay.knowledge.sync import VaultKnowledgeSync


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

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


NON_ELIGIBLE_FM = """\
---
title: Private Note
runtime_eligible: false
---
This should be skipped.
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
    non_eligible_dir = vault / "private"
    non_eligible_dir.mkdir(parents=True)
    (non_eligible_dir / "note.md").write_text(NON_ELIGIBLE_FM)
    (vault / "index.md").write_text("# Index")
    (vault / "AGENTS.md").write_text("# Agent rules")
    return vault


def make_manifest(vault: Path, entries: dict[str, dict]) -> None:
    path = vault / "sync-manifest.json"
    manifest = {"version": 1, "files": entries}
    path.write_text(json.dumps(manifest))


def hash_for(
    title: str, category: str, priority: str, tags: list[str], content: str
) -> str:
    tags_csv = ",".join(tags)
    payload = f"{title}|{category}|{priority}|{tags_csv}|{content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def mock_response(**overrides: object) -> MagicMock:
    r = MagicMock()
    r.json.return_value = {"recent_items": [{"item_id": 100}]} | overrides  # type: ignore[operator]
    return r


def make_mock_client() -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestParseFrontmatter:
    def test_parse_ok(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        market_dir = vault / "market"
        market_dir.mkdir(parents=True)
        (market_dir / "sma-crossover.md").write_text(SMA_CROSSOVER_FM)
        sync = VaultKnowledgeSync(vault)
        files = sync.read_vault_files()
        assert len(files) == 1
        vf = files[0]
        assert vf.title == "SMA Crossover"
        assert vf.category == "strategy_rule"
        assert vf.priority == "high"
        assert vf.tags == ["momentum", "trend", "trading"]
        assert vf.id == "market/sma-crossover"
        assert vf.source_type == "vault:market/sma-crossover"
        assert "Use SMA crossover" in vf.content

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "plain.md").write_text("Just text, no frontmatter.")
        sync = VaultKnowledgeSync(vault)
        files = sync.read_vault_files()
        assert len(files) == 0


class TestFilterRuntimeEligible:
    def test_only_true_passes(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        market_dir = vault / "market"
        market_dir.mkdir(parents=True)
        (market_dir / "sma-crossover.md").write_text(SMA_CROSSOVER_FM)
        private_dir = vault / "private"
        private_dir.mkdir()
        (private_dir / "note.md").write_text(NON_ELIGIBLE_FM)
        sync = VaultKnowledgeSync(vault)
        ids = {f.id for f in sync.read_vault_files()}
        assert ids == {"market/sma-crossover"}


class TestBuildPlan:
    def test_all_cases(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        known_hash = hash_for(
            title="Entry Rule",
            category="checklist",
            priority="medium",
            tags=["entry", "trading"],
            content="Check volume before entry.",
        )
        make_manifest(
            vault,
            {
                "market/sma-crossover": {
                    "id": "market/sma-crossover",
                    "item_id": 42,
                    "content_hash": "different_hash_123",
                },
                "strategy/entry-rule": {
                    "id": "strategy/entry-rule",
                    "item_id": 43,
                    "content_hash": known_hash,
                },
                "strategy/gone": {
                    "id": "strategy/gone",
                    "item_id": 44,
                    "content_hash": "x" * 64,
                },
            },
        )
        sync = VaultKnowledgeSync(vault)
        files = sync.read_vault_files()
        plan = sync.build_plan(files)
        assert len(plan) == 4

        by_id = {a.id: a for a in plan}
        assert by_id["market/sma-crossover"].action == "update"
        assert by_id["market/sma-crossover"].item_id == 42
        assert by_id["strategy/entry-rule"].action == "skip"
        assert by_id["strategy/gone"].action == "delete"
        assert by_id["strategy/gone"].item_id == 44
        assert by_id["observation/market-note"].action == "create"
        assert by_id["observation/market-note"].file is not None


class TestDryRun:
    def test_dry_run_does_not_call_api(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        sync = VaultKnowledgeSync(vault)
        plan = sync.build_plan()
        assert all(a.action in ("create", "skip") for a in plan)


class TestApply:
    @pytest.mark.asyncio
    async def test_apply_create(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        sync = VaultKnowledgeSync(vault)
        plan = sync.build_plan()
        create_actions = [a for a in plan if a.action == "create"]
        assert len(create_actions) == 3

        mock_client = make_mock_client()
        mock_client.post = AsyncMock(return_value=mock_response())

        with patch("httpx.AsyncClient", return_value=mock_client):
            await sync.apply([create_actions[0]])

        assert mock_client.post.call_count == 1
        assert mock_client.post.call_args[0][0] == "/knowledge/items/upsert"
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"]["title"] == "SMA Crossover"
        assert call_kwargs["json"]["source_type"] == "vault:market/sma-crossover"
        assert call_kwargs["json"]["external_id"] == "vault:market/sma-crossover"
        assert sync.manifest.files["market/sma-crossover"].item_id == 100

    @pytest.mark.asyncio
    async def test_apply_update(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        make_manifest(
            vault,
            {
                "market/sma-crossover": {
                    "id": "market/sma-crossover",
                    "item_id": 42,
                    "content_hash": "oldhash123",
                }
            },
        )
        sync = VaultKnowledgeSync(vault)
        plan = sync.build_plan()
        update_actions = [a for a in plan if a.action == "update"]
        assert len(update_actions) == 1

        mock_client = make_mock_client()
        mock_client.delete = AsyncMock(return_value=mock_response())
        mock_client.post = AsyncMock(return_value=mock_response())

        with patch("httpx.AsyncClient", return_value=mock_client):
            await sync.apply(update_actions)

        assert mock_client.delete.call_count == 0
        assert mock_client.post.call_count == 1
        assert mock_client.post.call_args[0][0] == "/knowledge/items/upsert"
        assert mock_client.post.call_args[1]["json"]["title"] == "SMA Crossover"
        assert (
            mock_client.post.call_args[1]["json"]["external_id"]
            == "vault:market/sma-crossover"
        )
        assert sync.manifest.files["market/sma-crossover"].item_id == 100

    @pytest.mark.asyncio
    async def test_apply_delete(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        make_manifest(
            vault,
            {
                "market/sma-crossover": {
                    "id": "market/sma-crossover",
                    "item_id": 42,
                    "content_hash": hash_for(
                        title="SMA Crossover",
                        category="strategy_rule",
                        priority="high",
                        tags=["momentum", "trend", "trading"],
                        content="Use SMA crossover on H1 for trend confirmation.",
                    ),
                },
                "strategy/gone": {
                    "id": "strategy/gone",
                    "item_id": 44,
                    "content_hash": "x" * 64,
                },
            },
        )
        sync = VaultKnowledgeSync(vault)
        plan = sync.build_plan()
        delete_actions = [a for a in plan if a.action == "delete"]
        assert len(delete_actions) == 1
        assert delete_actions[0].item_id == 44

        mock_client = make_mock_client()
        mock_client.delete = AsyncMock(return_value=mock_response())

        with patch("httpx.AsyncClient", return_value=mock_client):
            await sync.apply(delete_actions)

        mock_client.delete.assert_called_once_with("/knowledge/items/44")
        assert "strategy/gone" not in sync.manifest.files


DRAFT_FM = """\
---
title: Draft Strategy
runtime_eligible: true
status: draft
domain: strategy
---
This should be skipped.
"""


REVIEWED_FM = """\
---
title: Reviewed Strategy
runtime_eligible: true
status: peer_reviewed
domain: strategy
---
This should be synced.
"""


class TestStatusGate:
    def test_draft_skipped(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        strat_dir = vault / "strategy"
        strat_dir.mkdir(parents=True)
        (strat_dir / "draft-strat.md").write_text(DRAFT_FM)
        sync = VaultKnowledgeSync(vault)
        files = sync.read_vault_files()
        assert len(files) == 0

    def test_peer_reviewed_passes(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        strat_dir = vault / "strategy"
        strat_dir.mkdir(parents=True)
        (strat_dir / "reviewed-strat.md").write_text(REVIEWED_FM)
        sync = VaultKnowledgeSync(vault)
        files = sync.read_vault_files()
        assert len(files) == 1
        assert files[0].id == "strategy/reviewed-strat"

    def test_backtested_passes(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        strat_dir = vault / "strategy"
        strat_dir.mkdir(parents=True)
        fm = REVIEWED_FM.replace("peer_reviewed", "backtested")
        (strat_dir / "backtested-strat.md").write_text(fm)
        sync = VaultKnowledgeSync(vault)
        files = sync.read_vault_files()
        assert len(files) == 1

    def test_live_passes(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        strat_dir = vault / "strategy"
        strat_dir.mkdir(parents=True)
        fm = REVIEWED_FM.replace("peer_reviewed", "live")
        (strat_dir / "live-strat.md").write_text(fm)
        sync = VaultKnowledgeSync(vault)
        files = sync.read_vault_files()
        assert len(files) == 1


class TestManifestCrashSafety:
    @pytest.mark.asyncio
    async def test_manifest_saved_after_each_action(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        make_manifest(
            vault,
            {
                "market/sma-crossover": {
                    "id": "market/sma-crossover",
                    "item_id": 42,
                    "content_hash": "oldhash",
                },
            },
        )
        sync = VaultKnowledgeSync(vault)
        plan = sync.build_plan()
        assert any(a.action == "update" for a in plan)
        assert any(a.action == "create" for a in plan)

        mock_client = make_mock_client()
        call_count = 0

        async def mock_request(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return mock_response()
            raise RuntimeError("simulated crash on third action")

        mock_client.delete = AsyncMock(side_effect=mock_request)
        mock_client.post = AsyncMock(side_effect=mock_request)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(RuntimeError),
        ):
            await sync.apply(plan)

        manifest_path = vault / "sync-manifest.json"
        assert manifest_path.exists()
        saved = json.loads(manifest_path.read_text())
        assert "observation/market-note" in saved["files"]
        assert "strategy/entry-rule" in saved["files"]
        assert (
            saved["files"]["market/sma-crossover"]["content_hash"] == "oldhash"
        )  # update action crashed, hash unchanged


class TestUpdate404Tolerant:
    @pytest.mark.asyncio
    async def test_update_404_does_not_crash(self, tmp_path: Path) -> None:
        vault = make_vault(tmp_path)
        make_manifest(
            vault,
            {
                "market/sma-crossover": {
                    "id": "market/sma-crossover",
                    "item_id": 42,
                    "content_hash": "oldhash",
                },
            },
        )
        sync = VaultKnowledgeSync(vault)
        plan = sync.build_plan()
        update_actions = [a for a in plan if a.action == "update"]
        assert len(update_actions) == 1

        too_many_call = False

        async def delete_404(*args: object, **kwargs: object) -> MagicMock:
            nonlocal too_many_call
            if too_many_call:
                raise AssertionError("DELETE should not be called more than once")
            too_many_call = True
            r = MagicMock()
            r.status_code = 404
            return r

        mock_client = make_mock_client()
        mock_client.delete = AsyncMock(side_effect=delete_404)
        mock_client.post = AsyncMock(return_value=mock_response())

        with patch("httpx.AsyncClient", return_value=mock_client):
            await sync.apply(update_actions)

        assert mock_client.post.call_count == 1
        assert sync.manifest.files["market/sma-crossover"].item_id == 100
