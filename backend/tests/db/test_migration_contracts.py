from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _load_module(module_path: Path) -> object:
    spec = spec_from_file_location(module_path.stem, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _revision_id(path: Path) -> str:
    return str(getattr(_load_module(path), "revision"))


def _down_revision(path: Path) -> str | None:
    return getattr(_load_module(path), "down_revision")


def test_alembic_revision_ids_fit_default_version_table_limit() -> None:
    revisions = [
        _revision_id(path)
        for path in sorted(VERSIONS_DIR.glob("*.py"))
    ]

    assert revisions
    assert all(len(revision) <= 32 for revision in revisions)


def test_alembic_chain_0016_is_linear() -> None:
    """Verify that 0016_provider_pool chains linearly on top of 0015."""
    path_0016 = VERSIONS_DIR / "0016_provider_pool.py"
    path_0015 = VERSIONS_DIR / "0015_ai_agent_runs.py"
    path_0014 = VERSIONS_DIR / "0014_hypertable_indexes.py"

    assert path_0016.exists()
    assert path_0015.exists()
    assert path_0014.exists()

    assert _down_revision(path_0016) == _revision_id(path_0015)
    assert _down_revision(path_0015) == _revision_id(path_0014)
