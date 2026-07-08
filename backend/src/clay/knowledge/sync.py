from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from clay.knowledge.models import KnowledgeCreateCommand
from clay.knowledge.vault_core import (
    VaultFile,
    build_plan as core_build_plan,
    read_vault_files as core_read_vault_files,
)
from clay.knowledge.vault_core import PlanAction as CorePlanAction


@dataclass
class ManifestEntry:
    id: str
    item_id: int | None
    content_hash: str


@dataclass
class Manifest:
    version: int = 1
    files: dict[str, ManifestEntry] = field(default_factory=dict)


@dataclass
class PlanAction(CorePlanAction):
    item_id: int | None = None


class VaultKnowledgeSync:
    def __init__(
        self, vault_path: Path, base_url: str = "http://localhost:8000"
    ) -> None:
        self.vault_path = vault_path.resolve()
        self.base_url = base_url.rstrip("/")
        self.manifest_path = self.vault_path / "sync-manifest.json"
        self.manifest = self._load_manifest()

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def _load_manifest(self) -> Manifest:
        if not self.manifest_path.exists():
            return Manifest()
        raw = json.loads(self.manifest_path.read_text())
        files = {
            k: ManifestEntry(
                id=v["id"], item_id=v.get("item_id"), content_hash=v["content_hash"]
            )
            for k, v in raw.get("files", {}).items()
        }
        return Manifest(version=raw.get("version", 1), files=files)

    def _save_manifest(self) -> None:
        raw = {
            "version": self.manifest.version,
            "files": {
                eid: {
                    "id": entry.id,
                    "item_id": entry.item_id,
                    "content_hash": entry.content_hash,
                }
                for eid, entry in self.manifest.files.items()
            },
        }
        self.manifest_path.write_text(json.dumps(raw, indent=2))

    # ------------------------------------------------------------------
    # Vault reading
    # ------------------------------------------------------------------

    def read_vault_files(self) -> list[VaultFile]:
        return core_read_vault_files(self.vault_path)

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------

    def build_plan(self, files: list[VaultFile] | None = None) -> list[PlanAction]:
        if files is None:
            files = self.read_vault_files()

        known_hashes = {k: v.content_hash for k, v in self.manifest.files.items()}
        known_ids = set(self.manifest.files.keys())

        core_plan = core_build_plan(files, known_hashes, known_ids)

        plan: list[PlanAction] = []
        for a in core_plan:
            entry = self.manifest.files.get(a.id)
            plan.append(
                PlanAction(
                    action=a.action,
                    id=a.id,
                    file=a.file,
                    item_id=entry.item_id if entry else None,
                )
            )

        return plan

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    async def apply(self, plan: list[PlanAction]) -> None:
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            for action in plan:
                await self._execute_action(client, action)
                self._save_manifest()

    async def _execute_action(
        self, client: httpx.AsyncClient, action: PlanAction
    ) -> None:
        if action.action == "skip":
            return
        if action.action in ("create", "update"):
            assert action.file is not None
            cmd = self._to_command(action.file)
            r = await client.post(
                "/knowledge/items/upsert", json=cmd.model_dump(mode="json")
            )
            r.raise_for_status()
            data = r.json()
            item_id = data["recent_items"][0]["item_id"]
            self.manifest.files[action.id] = ManifestEntry(
                id=action.id, item_id=item_id, content_hash=action.file.content_hash
            )
        elif action.action == "delete":
            assert action.item_id is not None
            r = await client.delete(f"/knowledge/items/{action.item_id}")
            r.raise_for_status()
            self.manifest.files.pop(action.id, None)

    @staticmethod
    def _to_command(vf: VaultFile) -> KnowledgeCreateCommand:
        return KnowledgeCreateCommand(
            title=vf.title,
            category=vf.category,  # type: ignore[arg-type]
            priority=vf.priority,  # type: ignore[arg-type]
            tags=vf.tags,
            content=vf.content,
            source_type=vf.source_type,
            external_id=f"vault:{vf.id}",
        )

    # ------------------------------------------------------------------
    # Human-readable plan printer
    # ------------------------------------------------------------------

    @staticmethod
    def print_plan(plan: list[PlanAction]) -> None:
        if not plan:
            print("No actions.")
            return
        for a in plan:
            if a.action == "create":
                print(f"  CREATE  {a.id}")
            elif a.action == "update":
                print(f"  UPDATE  {a.id}  (item_id={a.item_id})")
            elif a.action == "delete":
                print(f"  DELETE  {a.id}  (item_id={a.item_id})")
            elif a.action == "skip":
                print(f"  SKIP    {a.id}")
        print(f"\nTotal: {len(plan)} actions")


def main() -> None:
    parser = argparse.ArgumentParser(description="Vault → Knowledge sync")
    parser.add_argument(
        "--vault", required=True, type=Path, help="Path to vault directory"
    )
    parser.add_argument(
        "--base-url", default="http://localhost:8000", help="Knowledge API base URL"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute plan against API (default: dry-run)",
    )
    args = parser.parse_args()

    sync = VaultKnowledgeSync(vault_path=args.vault, base_url=args.base_url)
    plan = sync.build_plan()
    VaultKnowledgeSync.print_plan(plan)

    if args.apply:
        asyncio.run(sync.apply(plan))
        print("Done — manifest updated.")


if __name__ == "__main__":
    main()
