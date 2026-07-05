from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx
from ruamel.yaml import YAML

from clay.knowledge.models import KnowledgeCreateCommand


_yaml = YAML(typ="safe")

_EXCLUDED_FILES = frozenset({"index.md", "log.md", "AGENTS.md", "sync-manifest.json"})

ActionKind = Literal["create", "update", "delete", "skip"]


@dataclass
class VaultFile:
    id: str
    title: str
    category: str
    priority: str
    tags: list[str]
    content: str
    content_hash: str
    source_type: str


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
class PlanAction:
    action: ActionKind
    id: str
    item_id: int | None = None
    file: VaultFile | None = None


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
        md_files = sorted(self.vault_path.rglob("*.md"))
        result: list[VaultFile] = []
        for path in md_files:
            rel = path.relative_to(self.vault_path)
            if rel.name in _EXCLUDED_FILES:
                continue
            parsed = self._parse_file(path, rel)
            if parsed is not None:
                result.append(parsed)
        return result

    def _parse_file(self, path: Path, rel: Path) -> VaultFile | None:
        text = path.read_text(encoding="utf-8")
        fm, body = self._split_frontmatter(text)
        if fm is None:
            return None
        if fm.get("runtime_eligible") is not True:
            return None
        title = fm.get("title", rel.stem)
        category = str(fm.get("kb_category", "note"))
        priority = str(fm.get("priority", "medium"))
        raw_tags: list[str] = list(fm.get("tags", []))
        domain = fm.get("domain")
        if domain:
            raw_tags.append(str(domain))
        content = body.strip()
        vid = rel.with_suffix("").as_posix()
        tags_csv = ",".join(raw_tags)
        payload = f"{title}|{category}|{priority}|{tags_csv}|{content}"
        content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return VaultFile(
            id=vid,
            title=title,
            category=category,
            priority=priority,
            tags=raw_tags,
            content=content,
            content_hash=content_hash,
            source_type=f"vault:{vid}",
        )

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[dict | None, str]:
        if not text.startswith("---"):
            return None, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return None, text
        fm_block = parts[1].strip()
        body = parts[2]
        try:
            fm = _yaml.load(fm_block)
        except Exception:
            return None, body
        if not isinstance(fm, dict):
            return None, body
        return fm, body

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------

    def build_plan(self, files: list[VaultFile] | None = None) -> list[PlanAction]:
        if files is None:
            files = self.read_vault_files()
        by_id = {f.id: f for f in files}
        plan: list[PlanAction] = []

        for vf in files:
            entry = self.manifest.files.get(vf.id)
            if entry is None:
                plan.append(PlanAction(action="create", id=vf.id, file=vf))
            elif entry.content_hash == vf.content_hash:
                plan.append(
                    PlanAction(action="skip", id=vf.id, item_id=entry.item_id, file=vf)
                )
            else:
                plan.append(
                    PlanAction(
                        action="update", id=vf.id, item_id=entry.item_id, file=vf
                    )
                )

        for eid, entry in self.manifest.files.items():
            if eid not in by_id:
                plan.append(PlanAction(action="delete", id=eid, item_id=entry.item_id))

        plan.sort(
            key=lambda a: (
                {"delete": 0, "create": 1, "update": 2, "skip": 3}[a.action],
                a.id,
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
        if action.action == "create":
            assert action.file is not None
            cmd = self._to_command(action.file)
            r = await client.post("/knowledge/items", json=cmd.model_dump(mode="json"))
            r.raise_for_status()
            data = r.json()
            new_id = data["recent_items"][0]["item_id"]
            self.manifest.files[action.id] = ManifestEntry(
                id=action.id, item_id=new_id, content_hash=action.file.content_hash
            )
        elif action.action == "update":
            assert action.file is not None
            assert action.item_id is not None
            r = await client.delete(f"/knowledge/items/{action.item_id}")
            r.raise_for_status()
            cmd = self._to_command(action.file)
            r = await client.post("/knowledge/items", json=cmd.model_dump(mode="json"))
            r.raise_for_status()
            data = r.json()
            new_id = data["recent_items"][0]["item_id"]
            self.manifest.files[action.id] = ManifestEntry(
                id=action.id, item_id=new_id, content_hash=action.file.content_hash
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
