from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from clay.knowledge.vault_core import (
    VaultFile,
    build_plan as core_build_plan,
    read_vault_files as core_read_vault_files,
)
from clay.knowledge.vault_core import PlanAction as CorePlanAction


from collections.abc import MutableMapping


class _VersionRestorer:
    def __init__(
        self, headers: MutableMapping[str, str], old_version: str | None
    ) -> None:
        self._headers = headers
        self._old = old_version

    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        if self._old is not None:
            self._headers["notion-version"] = self._old
        else:
            self._headers.pop("notion-version", None)


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

    async def find_page_by_clay_id(
        self, database_id: str, clay_id: str
    ) -> str | None: ...


def _build_properties(file: VaultFile) -> dict:
    domain = file.id.split("/")[0] if "/" in file.id else ""
    tags = [t for t in file.tags if t != domain]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "Title": {"title": [{"type": "text", "text": {"content": file.title}}]},
        "Clay ID": {"rich_text": [{"type": "text", "text": {"content": file.id}}]},
        "Content Hash": {
            "rich_text": [{"type": "text", "text": {"content": file.content_hash}}]
        },
        "Category": {"select": {"name": file.category}},
        "Priority": {"select": {"name": file.priority}},
        "Domain": {"select": {"name": domain}},
        "Tags": {"multi_select": [{"name": t} for t in tags]},
        "Source": {
            "rich_text": [{"type": "text", "text": {"content": file.source_type}}]
        },
        "Synced At": {"date": {"start": now}},
    }


class RealNotionUpsertClient:
    _QUERY_API_VERSION = "2022-06-28"
    _MARKDOWN_API_VERSION = "2025-09-03"

    @staticmethod
    def _should_force_ipv4() -> bool:
        return os.environ.get("CLAY_NOTION_FORCE_IPV4", "").lower() in (
            "true",
            "1",
            "yes",
        )

    def __init__(self, token: str) -> None:
        import httpx
        from notion_client import Client

        if self._should_force_ipv4():
            transport = httpx.HTTPTransport(local_address="0.0.0.0")
            httpx_client = httpx.Client(transport=transport)
        else:
            httpx_client = httpx.Client()
        self._client = Client(auth=token, client=httpx_client)
        self._client.client.headers["notion-version"] = self._QUERY_API_VERSION

    def _api_version(self, version: str):
        old = self._client.client.headers.get("notion-version")
        self._client.client.headers["notion-version"] = version
        return _VersionRestorer(self._client.client.headers, old)

    async def create_page(self, database_id: str, file: VaultFile) -> str:
        with self._api_version(self._MARKDOWN_API_VERSION):
            r = self._client.pages.create(
                parent={"database_id": database_id, "type": "database_id"},
                properties=_build_properties(file),
                markdown=file.content or "\u22ee",
            )
        assert isinstance(r, dict)
        return r["id"]

    async def update_page(self, page_id: str, file: VaultFile) -> None:
        with self._api_version(self._MARKDOWN_API_VERSION):
            self._client.pages.update(
                page_id=page_id, properties=_build_properties(file)
            )
            self._client.pages.update_markdown(
                page_id=page_id,
                type="replace_content",
                replace_content={"new_str": file.content or "\u22ee"},
            )

    async def archive_page(self, page_id: str) -> None:
        self._client.pages.update(page_id=page_id, archived=True)

    async def find_page_by_clay_id(self, database_id: str, clay_id: str) -> str | None:
        r = self._client.request(
            path=f"databases/{database_id}/query",
            method="POST",
            body={
                "filter": {
                    "property": "Clay ID",
                    "rich_text": {"equals": clay_id},
                },
                "page_size": 10,
            },
        )
        assert isinstance(r, dict)
        for page in r.get("results", []):
            if not page.get("archived", False):
                return page["id"]
        return None


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

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    async def apply(
        self, plan: list[NotionPlanAction], client: NotionUpsertClient
    ) -> None:
        for action in plan:
            if action.action == "skip":
                continue
            if action.action in ("create", "update"):
                await self._execute_upsert(client, action)
            elif action.action == "delete":
                await self._execute_archive(client, action)
            self.manifest.save(self.manifest_path)

    async def _execute_upsert(
        self, client: NotionUpsertClient, action: NotionPlanAction
    ) -> None:
        assert action.file is not None
        if action.action == "create":
            existing_page_id = await client.find_page_by_clay_id(
                self.config.database_id, action.id
            )
            if existing_page_id is not None:
                await client.update_page(existing_page_id, action.file)
                self.manifest.files[action.id] = NotionManifestEntry(
                    id=action.id,
                    page_id=existing_page_id,
                    content_hash=action.file.content_hash,
                )
                print(f"  RECONCILED→UPDATE  {action.id}  (page_id={existing_page_id})")
            else:
                page_id = await client.create_page(self.config.database_id, action.file)
                self.manifest.files[action.id] = NotionManifestEntry(
                    id=action.id,
                    page_id=page_id,
                    content_hash=action.file.content_hash,
                )
                print(f"  CREATED  {action.id}  (page_id={page_id})")
        elif action.action == "update":
            assert action.page_id is not None
            await client.update_page(action.page_id, action.file)
            self.manifest.files[action.id].content_hash = action.file.content_hash
            print(f"  UPDATED  {action.id}  (page_id={action.page_id})")

    async def _execute_archive(
        self, client: NotionUpsertClient, action: NotionPlanAction
    ) -> None:
        if action.page_id is None:
            self.manifest.files.pop(action.id, None)
            print(f"  ARCHIVED  {action.id}  (page_id=None, manifest-only)")
            return
        await client.archive_page(action.page_id)
        self.manifest.files.pop(action.id, None)
        print(f"  ARCHIVED  {action.id}  (page_id={action.page_id})")

    @staticmethod
    def print_plan(plan: list[NotionPlanAction]) -> None:
        if not plan:
            print("No actions.")
            return
        counts: dict[str, int] = {}
        for a in plan:
            counts[a.action] = counts.get(a.action, 0) + 1
            if a.action == "create":
                print(f"  CREATE  {a.id}")
            elif a.action == "update":
                print(f"  UPDATE  {a.id}  (page_id={a.page_id})")
            elif a.action == "delete":
                print(f"  DELETE  {a.id}  (page_id={a.page_id})")
            elif a.action == "skip":
                print(f"  SKIP    {a.id}")
        parts = [f"{k.upper()} {v}" for k, v in sorted(counts.items())]
        print(f"\n  {' · '.join(parts)}")
        print(f"  Total: {len(plan)} actions")


def _exit(code: int, msg: str = "") -> None:
    if msg:
        print(msg)
    sys.exit(code)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vault \u2192 Notion knowledge sync (dry-run by default)"
    )
    parser.add_argument(
        "--vault", required=True, type=Path, help="Path to vault directory"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute plan against Notion API (exit: 0=ok, 1=config/usage, 2=runtime)",
    )
    args = parser.parse_args()

    vault_path: Path = args.vault
    if not vault_path.is_dir():
        _exit(1, f"error: vault path not found or not a directory: {vault_path}")

    config = NotionPublisherConfig.from_env(vault_path=vault_path)
    publisher = NotionKnowledgePublisher(config)
    plan: list[NotionPlanAction] = []
    try:
        plan = publisher.build_plan()
    except Exception as exc:
        _exit(1, f"error: failed to read vault: {exc}")

    NotionKnowledgePublisher.print_plan(plan)

    if not args.apply:
        return

    if not config.database_id or not config.token:
        _exit(1, "error: CLAY_NOTION_KB_DB and CLAY_NOTION_TOKEN must be set")

    try:
        client = RealNotionUpsertClient(token=config.token)
        asyncio.run(publisher.apply(plan, client))
    except Exception as exc:
        _exit(2, f"error: apply failed: {exc}")

    print("Done \u2014 notion manifest updated.")


if __name__ == "__main__":
    main()
