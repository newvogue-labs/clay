import shutil
import tomllib
from pathlib import Path
from typing import Any

from clay.config.models import RiskConfig, RuntimeConfig
from clay.config.paths import XdgPaths, build_xdg_paths


CONFIG_MODELS = {
    "runtime": RuntimeConfig,
    "risk": RiskConfig,
}


class UnknownConfigScopeError(KeyError):
    """Raised when a caller asks for a config scope Clay does not know."""


class ConfigLoader:
    """Loads Clay configuration from XDG-aware paths with last-valid backups."""

    def __init__(self, paths: XdgPaths | None = None) -> None:
        self.paths = paths or build_xdg_paths()
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.paths.config_dir / ".last_valid"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def write_default_configs(self) -> None:
        self._write_default_scope("runtime")
        self._write_default_scope("risk")

    def ensure_default_configs(self) -> None:
        for scope in self.list_scopes():
            if not self._scope_path(scope).exists():
                self._write_default_scope(scope)

    def list_scopes(self) -> list[str]:
        return sorted(CONFIG_MODELS)

    def load_scope(self, scope: str) -> RuntimeConfig | RiskConfig:
        self.ensure_default_configs()
        return self._load_scope(scope)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            scope: config.model_dump(mode="json")
            for scope, config in self.load_all().items()
        }

    def apply_config(self, scope: str, payload: dict[str, Any]) -> dict[str, Any]:
        model_cls = self._get_model_cls(scope)
        validated = model_cls.model_validate(payload)
        target = self._scope_path(scope)
        previous_text = target.read_text(encoding="utf-8") if target.exists() else None

        target.write_text(
            self._dump_toml(validated.model_dump(mode="json")),
            encoding="utf-8",
        )

        try:
            configs = self.load_all()
        except ValueError:
            self._rollback_scope(scope, previous_text)
            raise

        return configs[scope].model_dump(mode="json")

    def write_runtime_defaults(self) -> None:
        """Compatibility helper for callers that want a named bootstrap step."""
        self._write_default_scope("runtime")

    def _write_default_scope(self, scope: str) -> None:
        target = self._scope_path(scope)
        if scope == "runtime":
            target.write_text(
            'work_window_start = "09:00"\n'
            'work_window_end = "22:00"\n'
            'default_state = "background_monitoring"\n',
            encoding="utf-8",
        )
            return
        if scope == "risk":
            target.write_text(
                "confidence_warning_threshold = 0.6\n"
                "degraded_confidence_penalty = 0.2\n"
                "\n"
                "[kelly]\n"
                "lambda = 0.25\n"
                "cap = 0.02\n"
                "min_ev = 0.15\n"
                "equity_base = 1.0\n"
                "\n"
                "[calibration]\n"
                "min_outcomes_for_recalibration = 30\n"
                "\n"
                "[session_limits]\n"
                "max_drawdown_pct = 15.0\n"
                "max_consecutive_losses = 3\n"
                "cooldown_minutes = 60\n"
                "drawdown_window_hours = 24\n"
                "max_concurrent_sessions = 1\n"
                "max_total_exposure_pct = 4.0\n"
                "per_session_loss_warn_pct = 8.0\n",
                encoding="utf-8",
            )
            return
        raise UnknownConfigScopeError(scope)

    def apply_raw_text(self, scope: str, text: str) -> Path:
        target = self._scope_path(scope)
        target.write_text(text, encoding="utf-8")
        return target

    def load_all(self) -> dict[str, RuntimeConfig | RiskConfig]:
        self.ensure_default_configs()
        configs = {
            scope: self._load_scope(scope)
            for scope in self.list_scopes()
        }
        for scope in configs:
            shutil.copy2(self._scope_path(scope), self._backup_path(scope))
        return configs

    def restore_last_valid(self, scope: str) -> Path:
        self._get_model_cls(scope)
        backup = self._backup_path(scope)
        target = self._scope_path(scope)
        if not backup.exists():
            raise FileNotFoundError(f"no backup exists for {scope}")
        shutil.copy2(backup, target)
        return target

    def _load_scope(self, scope: str) -> RuntimeConfig | RiskConfig:
        model_cls = self._get_model_cls(scope)
        path = self._scope_path(scope)
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return model_cls.model_validate(data)

    def _get_model_cls(self, scope: str) -> type[RuntimeConfig] | type[RiskConfig]:
        try:
            return CONFIG_MODELS[scope]
        except KeyError as exc:
            raise UnknownConfigScopeError(scope) from exc

    def _scope_path(self, scope: str) -> Path:
        return self.paths.config_dir / f"{scope}.toml"

    def _backup_path(self, scope: str) -> Path:
        return self.backup_dir / f"{scope}.toml"

    def _rollback_scope(self, scope: str, previous_text: str | None) -> None:
        target = self._scope_path(scope)
        backup = self._backup_path(scope)
        if backup.exists():
            shutil.copy2(backup, target)
            return
        if previous_text is None:
            target.unlink(missing_ok=True)
            self._write_default_scope(scope)
            return
        target.write_text(previous_text, encoding="utf-8")

    def _dump_toml(self, data: dict[str, Any]) -> str:
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"\n[{key}]")
                for sk, sv in value.items():
                    sk_display = "lambda" if sk == "lambda_" else sk
                    if isinstance(sv, str):
                        lines.append(f'{sk_display} = "{sv}"')
                    elif isinstance(sv, bool):
                        lines.append(f"{sk_display} = {'true' if sv else 'false'}")
                    else:
                        lines.append(f"{sk_display} = {sv}")
            elif isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            elif isinstance(value, bool):
                lines.append(f"{key} = {'true' if value else 'false'}")
            else:
                lines.append(f"{key} = {value}")
        return "\n".join(lines) + "\n"
