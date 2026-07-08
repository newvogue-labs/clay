from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from clay.knowledge.vault_core import (
    VaultFile,
    build_plan as core_build_plan,
    read_vault_files as core_read_vault_files,
)
from clay.knowledge.vault_core import PlanAction as CorePlanAction


@dataclass(frozen=True)
class NotionPublisherConfig:
    vault_path: Path
    database_id: str = ""
    token: str = ""

    @classmethod
    def from_env(cls, vault_path: Path) -> NotionPublisherConfig:
        return cls(
            vault_path=vault_path,
            database_id=os.environ.get("CLAY_NOTION_KB_DB", ""),
            token=os.environ.get("CLAY_NOTION_TOKEN", ""),
        )


@dataclass
class NotionManifestEntry:
    id: str
    page_id: str | None
    content_hash: str


@dataclass
class NotionManifest:
    version: int = 1
    files: dict[str, NotionManifestEntry] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> NotionManifest:
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text())
        files = {
            k: NotionManifestEntry(
                id=v["id"], page_id=v.get("page_id"), content_hash=v["content_hash"]
            )
            for k, v in raw.get("files", {}).items()
        }
        return cls(version=raw.get("version", 1), files=files)

    def save(self, path: Path) -> None:
        raw = {
            "version": self.version,
            "files": {
                eid: {
                    "id": entry.id,
                    "page_id": entry.page_id,
                    "content_hash": entry.content_hash,
                }
                for eid, entry in self.files.items()
            },
        }
        path.write_text(json.dumps(raw, indent=2))


@dataclass
class NotionPlanAction(CorePlanAction):
    page_id: str | None = None


@runtime_checkable
class NotionUpsertClient(Protocol):
    async def create_page(self, database_id: str, file: VaultFile) -> str: ...

    async def update_page(self, page_id: str, file: VaultFile) -> None: ...

    async def archive_page(self, page_id: str) -> None: ...


class NotionKnowledgePublisher:
    def __init__(self, config: NotionPublisherConfig) -> None:
        self.config = config
        self.vault_path = config.vault_path.resolve()
        self.manifest_path = self.vault_path / "notion-sync-manifest.json"
        self.manifest = NotionManifest.load(self.manifest_path)

    def read_vault_files(self) -> list[VaultFile]:
        return core_read_vault_files(self.vault_path)

    def build_plan(
        self, files: list[VaultFile] | None = None
    ) -> list[NotionPlanAction]:
        if files is None:
            files = self.read_vault_files()

        known_hashes = {k: v.content_hash for k, v in self.manifest.files.items()}
        known_ids = set(self.manifest.files.keys())

        core_plan = core_build_plan(files, known_hashes, known_ids)

        plan: list[NotionPlanAction] = []
        for a in core_plan:
            entry = self.manifest.files.get(a.id)
            plan.append(
                NotionPlanAction(
                    action=a.action,
                    id=a.id,
                    file=a.file,
                    page_id=entry.page_id if entry else None,
                )
            )

        return plan

    async def apply(
        self, plan: list[NotionPlanAction], client: NotionUpsertClient | None = None
    ) -> None:
        raise NotImplementedError("apply lands in S2-3")

    @staticmethod
    def print_plan(plan: list[NotionPlanAction]) -> None:
        if not plan:
            print("No actions.")
            return
        for a in plan:
            if a.action == "create":
                print(f"  CREATE  {a.id}")
            elif a.action == "update":
                print(f"  UPDATE  {a.id}  (page_id={a.page_id})")
            elif a.action == "delete":
                print(f"  DELETE  {a.id}  (page_id={a.page_id})")
            elif a.action == "skip":
                print(f"  SKIP    {a.id}")
        print(f"\nTotal: {len(plan)} actions")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vault → Notion knowledge sync (dry-run by default)"
    )
    parser.add_argument(
        "--vault", required=True, type=Path, help="Path to vault directory"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute plan against Notion API (stubbed until S2-3)",
    )
    args = parser.parse_args()

    config = NotionPublisherConfig.from_env(vault_path=args.vault)
    publisher = NotionKnowledgePublisher(config)
    plan = publisher.build_plan()
    NotionKnowledgePublisher.print_plan(plan)

    if args.apply:
        print("apply not yet implemented — S2-3")
        print("  (use --apply only after notion-client is pinned and wired)")


if __name__ == "__main__":
    main()
