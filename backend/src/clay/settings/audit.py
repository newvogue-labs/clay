"""FIX-C: AuditSettings — operator-tunable knobs for ``AuditWriter``.

Mirrors the ``IngestionSettings`` / ``SchedulerSettings`` pattern
(pydantic-settings, ``env_prefix``, ``extra="ignore"``) so operators
get a single familiar env surface for runtime-configurable audit
rotation.

Read at the composition boundary (``build_services`` in
``clay.bootstrap``) and passed into ``AuditWriter`` via DI — the
settings module is never imported by ``AuditWriter`` itself (avoids
the A6 cross-layer-import risk).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuditSettings(BaseSettings):
    """FIX-C: configuration for ``AuditWriter`` retention.

    * ``max_bytes`` — size threshold that triggers rotation.
      ``<= 0`` disables rotation entirely (the file grows unbounded).
      Default 5_000_000 (5 MiB). Env: ``CLAY_AUDIT_MAX_BYTES``.
    * ``backup_count`` — number of rotated copies retained
      (``audit.jsonl.1`` ... ``audit.jsonl.N``). ``<= 0`` rotates by
      deleting the active file (no backups kept). Default 5.
      Env: ``CLAY_AUDIT_BACKUP_COUNT``.

    Thread-safety of writes is guaranteed by ``AuditWriter`` itself
    (in-process ``threading.Lock`` per ADR-007 single-worker
    contract). Cross-process locking is explicitly OUT of scope.
    """

    model_config = SettingsConfigDict(
        env_prefix="CLAY_AUDIT_",
        extra="ignore",
    )

    max_bytes: int = 5_000_000
    backup_count: int = 5
