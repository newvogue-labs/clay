"""ProviderPoolReconcileJob — scheduler-driven reconcile of provider pool → LiteLLM config.

S3d-2: periodic sync job that:

1. Opens a DB session, reads enabled deployments from ``SqlProviderPoolRepository``.
2. Calls ``ConfigWriter.reconcile(rows)`` (render → health-check → validate → apply_live).
3. Logs the ``ApplyReport`` structurally.
4. Never crashes (``reconcile()`` returns ``ApplyReport`` with error status; the
   ``_run_safely`` wrapper handles unexpected exceptions).

Flag-gated by ``SchedulerSettings.provider_pool_reconcile_enabled`` (default ``False``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from clay.ai_control.config_reconciler import (
    ConfigReconciler,
    ConfigWriter,
)
from clay.ai_control.provider_pool_repository import SqlProviderPoolRepository

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path("/etc/clay/litellm/config.yaml")


class ProviderPoolReconcileJob:
    """Periodic job: DB → render → reconcile → log ``ApplyReport``.

    Sync callable for the APScheduler ThreadPoolExecutor (``executor="default"``).
    Each tick opens its own session, reads deployments, calls ``reconcile()``,
    and logs the result.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        config_path: Path | None = None,
    ) -> None:
        self._session_factory = session_factory
        _path = config_path or _CONFIG_PATH
        self._reconciler = ConfigReconciler(_path)
        self._writer = ConfigWriter(self._reconciler)

    def run_once(self) -> None:
        """Execute one reconcile tick: DB → render → reconcile → log.

        Never raises: unexpected exceptions are caught and logged so the
        scheduler thread (``_run_safely`` wrapper) is never crashed.
        """
        with self._session_factory() as session:
            repo = SqlProviderPoolRepository(session)
            rows = list(repo.list_enabled_deployments())

        try:
            report = self._writer.reconcile(rows)
        except Exception:
            logger.exception(
                "Provider pool reconcile crashed: unexpected exception",
            )
            return

        logger.info(
            "Provider pool reconcile: status=%s available=%d "
            "by_model=%s restarted=%s rolled_back=%s backup=%s",
            report.status,
            report.available_total,
            report.by_model_name,
            report.restart_ok,
            report.rolled_back,
            report.backup_path,
        )

        if report.status == "degraded":
            logger.warning(
                "Provider pool degraded: available=%d by_model=%s — "
                "config NOT written, last-good preserved",
                report.available_total,
                report.by_model_name,
            )
