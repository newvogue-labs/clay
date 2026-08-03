import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class XdgPaths:
    config_dir: Path
    data_dir: Path
    state_dir: Path
    cache_dir: Path


def _xdg_path(key: str, default: Path) -> Path:
    """Резолв XDG-каталога: заданная пустая строка = «не задан» → дефолт (D-64).

    ``os.getenv(key, default)`` для заданной пустой переменной вернул бы
    ``""``, а ``Path("")`` увёл бы путь в относительный ``./clay``. Форма
    ``value or default`` трактует пустую строку как отсутствие переменной.
    Единая точка резолва всех ``XDG_*_HOME`` (D-64, по образцу D-45).
    """
    value = os.getenv(key)
    return Path(value) if value else default


def build_xdg_paths(app_name: str = "clay") -> XdgPaths:
    home = Path.home()
    return XdgPaths(
        config_dir=_xdg_path("XDG_CONFIG_HOME", home / ".config") / app_name,
        data_dir=_xdg_path("XDG_DATA_HOME", home / ".local/share") / app_name,
        state_dir=_xdg_path("XDG_STATE_HOME", home / ".local/state") / app_name,
        cache_dir=_xdg_path("XDG_CACHE_HOME", home / ".cache") / app_name,
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

    Резолв базы — через общий ``_xdg_path`` (D-64, канон D-45): пустая
    строка ``XDG_STATE_HOME`` трактуется как «не задан», иначе ``Path("")``
    увёл бы журнал в ``./clay/audit.jsonl``.
    """
    if state_dir is None:
        home = Path.home()
        state_dir = _xdg_path("XDG_STATE_HOME", home / ".local/state") / "clay"
    journal = state_dir / "audit.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    return journal
