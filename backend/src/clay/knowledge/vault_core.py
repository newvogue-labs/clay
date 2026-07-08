from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ruamel.yaml import YAML


_yaml = YAML(typ="safe")

_EXCLUDED_FILES = frozenset({"index.md", "log.md", "AGENTS.md", "sync-manifest.json"})
_SYNCABLE_STATUSES = frozenset({"peer_reviewed", "backtested", "live"})

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
class PlanAction:
    action: ActionKind
    id: str
    file: VaultFile | None = None


def split_frontmatter(text: str) -> tuple[dict | None, str]:
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


def parse_vault_file(path: Path, rel: Path) -> VaultFile | None:
    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    if fm is None:
        return None
    if fm.get("runtime_eligible") is not True:
        return None
    if fm.get("status") not in _SYNCABLE_STATUSES:
        return None
    title = str(fm.get("title", rel.stem))
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


def read_vault_files(vault_path: Path) -> list[VaultFile]:
    md_files = sorted(vault_path.rglob("*.md"))
    result: list[VaultFile] = []
    for path in md_files:
        rel = path.relative_to(vault_path)
        if rel.name in _EXCLUDED_FILES:
            continue
        parsed = parse_vault_file(path, rel)
        if parsed is not None:
            result.append(parsed)
    return result


def build_plan(
    files: list[VaultFile],
    known_hashes: dict[str, str],
    known_ids: set[str],
) -> list[PlanAction]:
    by_id = {f.id: f for f in files}
    plan: list[PlanAction] = []

    for vf in files:
        if vf.id not in known_ids:
            plan.append(PlanAction(action="create", id=vf.id, file=vf))
        elif known_hashes.get(vf.id) == vf.content_hash:
            plan.append(PlanAction(action="skip", id=vf.id))
        else:
            plan.append(PlanAction(action="update", id=vf.id, file=vf))

    for eid in known_ids:
        if eid not in by_id:
            plan.append(PlanAction(action="delete", id=eid))

    plan.sort(
        key=lambda a: (
            {"delete": 0, "create": 1, "update": 2, "skip": 3}[a.action],
            a.id,
        )
    )
    return plan
