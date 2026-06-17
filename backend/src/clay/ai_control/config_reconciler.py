from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Sequence

from ruamel.yaml import YAML

from clay.ai_control.provider_pool import DeploymentRow


_AVAILABLE = "available"
_KEY_PREFIX = "os.environ/"


@dataclass
class ProposedConfig:
    document: dict
    yaml: str


@dataclass
class ParityReport:
    is_equivalent: bool
    added: list[tuple[str, str]] = field(default_factory=list)
    removed: list[tuple[str, str]] = field(default_factory=list)
    changed: list[tuple[str, str, dict, dict]] = field(default_factory=list)


class ConfigReconciler:
    """Reconciles provider_deployments from the database against the
    live LiteLLM ``config.yaml``.

    This is a *read-only* renderer — ``render()`` produces a
    ``ProposedConfig`` in memory, **never** writes to disk.
    """

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.indent(mapping=2, sequence=4, offset=2)

    def render(self, rows: Sequence[DeploymentRow]) -> ProposedConfig:
        available = self._filter_available(rows)
        model_list = [self._row_to_entry(r) for r in available]

        doc = self._load_round_trip()
        doc["model_list"] = model_list

        buf = StringIO()
        self._yaml.dump(doc, buf)
        return ProposedConfig(document=doc, yaml=buf.getvalue())

    def diff(self, proposed_yaml: str) -> ParityReport:
        live = self._parse_semantic(self._config_path)
        prop = self._parse_semantic_str(proposed_yaml)

        live_models = set(live["model_index"])
        prop_models = set(prop["model_index"])

        added = sorted(prop_models - live_models)
        removed = sorted(live_models - prop_models)
        common = live_models & prop_models
        changed: list[tuple[str, str, dict, dict]] = []
        for key in sorted(common):
            if live["model_index"][key] != prop["model_index"][key]:
                changed.append((*key, live["model_index"][key], prop["model_index"][key]))

        rest_equal = live["rest"] == prop["rest"]

        return ParityReport(
            is_equivalent=(not added and not removed and not changed and rest_equal),
            added=added,
            removed=removed,
            changed=changed,
        )

    def _filter_available(self, rows: Sequence[DeploymentRow]) -> list[DeploymentRow]:
        return [r for r in rows if r.key_state is None or r.key_state == _AVAILABLE]

    def _row_to_entry(self, row: DeploymentRow) -> dict:
        lp: dict[str, object] = {"model": row.upstream_model}
        if row.base_url is not None:
            lp["api_base"] = row.base_url
        if row.key_ref is not None:
            lp["api_key"] = f"{_KEY_PREFIX}{row.key_ref}"
        if row.params:
            for k, v in sorted(row.params.items()):
                lp[k] = v
        return {"model_name": row.model_name, "litellm_params": lp}

    def _load_round_trip(self) -> dict:
        with open(self._config_path) as f:
            doc = self._yaml.load(f)
        return doc if doc is not None else {}

    def _parse_semantic(self, path: Path) -> dict:
        with open(path) as f:
            raw = f.read()
        return self._parse_semantic_str(raw)

    @staticmethod
    def _parse_semantic_str(raw: str) -> dict:
        safe = YAML(typ="safe")
        data = safe.load(raw)
        if data is None:
            return {"model_index": {}, "rest": {}}
        model_index: dict[tuple[str, str], dict] = {}
        for entry in data.get("model_list") or []:
            lp = entry.get("litellm_params") or {}
            model = lp.get("model") or ""
            key = (entry["model_name"], str(model))
            canonical = {k: v for k, v in sorted(lp.items()) if v is not None}
            model_index[key] = canonical
        rest = {k: v for k, v in data.items() if k != "model_list"}
        return {"model_index": model_index, "rest": rest}
