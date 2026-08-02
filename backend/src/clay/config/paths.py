import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class XdgPaths:
    config_dir: Path
    data_dir: Path
    state_dir: Path
    cache_dir: Path


def build_xdg_paths(app_name: str = "clay") -> XdgPaths:
    home = Path.home()
    state_env = os.getenv("XDG_STATE_HOME")
    return XdgPaths(
        config_dir=Path(os.getenv("XDG_CONFIG_HOME", home / ".config")) / app_name,
        data_dir=Path(os.getenv("XDG_DATA_HOME", home / ".local/share")) / app_name,
        state_dir=(Path(state_env) if state_env else home / ".local/state") / app_name,
        cache_dir=Path(os.getenv("XDG_CACHE_HOME", home / ".cache")) / app_name,
    )


def resolve_audit_journal_path(state_dir: Path | None = None) -> Path:
    """Единая точка резолвинга пути аудит-журнала (D-45).

    Если ``state_dir`` передан (изолированный каталог — интеграционные
    тесты) — журнал строится из него: ``state_dir / имя файла журнала``.
    Иначе ``state_dir`` выводится из окружения: base = $XDG_STATE_HOME
    (если задан и непустой), иначе дефолтная база ~/.local/state; каталог
    приложения = base / "clay".

    Имя файла журнала ("audit.jsonl") живёт в одном месте; родительская
    директория создаётся при необходимости. Все чтения/записи журнала идут
    только через этот резолвер — единственная точка фактического пути.

    Отличие от ``build_xdg_paths``: пустая строка ``XDG_STATE_HOME``
    трактуется как «не задан» (``os.getenv`` вернул бы ``""``, а
    ``Path("")`` увёл бы журнал в ``./clay/audit.jsonl``).
    """
    if state_dir is None:
        home = Path.home()
        base_env = os.getenv("XDG_STATE_HOME")
        state_dir = (Path(base_env) if base_env else home / ".local/state") / "clay"
    journal = state_dir / "audit.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    return journal
