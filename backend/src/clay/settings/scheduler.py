"""SchedulerSettings — operator-tunable knobs for the Clay scheduler.

Read by ``ClayScheduler`` and the B3b+ jobs. Mirrors the
``IngestionSettings`` pattern (pydantic-settings, env_prefix,
``extra="ignore"``) so operators get a single familiar env surface
for runtime-configurable intervals.

B3a: only ``enabled`` and the health-tick fields are *used*. The
reliability and ingestion intervals are reserved for B4 and B5
respectively — kept here so the schema is stable across slices
(no churn for the operator who already set
``CLAY_SCHEDULER_RELIABILITY_INTERVAL_SECONDS`` in dev).
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchedulerSettings(BaseSettings):
    """Operator-tunable scheduler configuration.

    All intervals are in seconds. Defaults follow the B0 / B2
    architecture:

    * ``health_tick_interval_seconds = 30`` (B0 §11.5)
    * ``health_stale_after_seconds = 60`` (B2; B3 invariant below)
    * ``reliability_enabled = True`` (B4 flag-gate; env
      ``CLAY_SCHEDULER_RELIABILITY_ENABLED``)
    * ``reliability_recheck_interval_seconds = 300`` (B0 §11; B4)
    * ``ingestion_cycle_interval_seconds = 60`` (B0 §11; B5)
    """

    model_config = SettingsConfigDict(
        env_prefix="CLAY_SCHEDULER_",
        extra="ignore",
    )

    enabled: bool = True

    # B4: gate for the ``reliability-recheck`` job. ``False`` skips
    # registration (with no warning — a documented operator opt-out,
    # not a misconfiguration). Default ``True`` keeps Wave B / B4
    # behaviour for everyone who did not opt out.
    reliability_enabled: bool = True

    # B5: gate for the ``ingestion-cycle`` job. ``False`` skips
    # registration (with no warning — a documented operator opt-out).
    # Default ``True`` mirrors the B4 ``reliability_enabled`` shape.
    ingestion_enabled: bool = True

    # MP1: gate for the ``ops-retention`` prune-job. ``False`` skips
    # registration (with no warning — a documented operator opt-out).
    # Default ``True`` — retention is safety-critical; deliberate opt-out only.
    ops_retention_enabled: bool = True

    # B3a: drive the (future) health-tick job. The ``60s`` default
    # replaced the B2 hard-coded ``_DEFAULT_HEALTH_STALE_AFTER_SECONDS``
    # constant in ``bootstrap.py``.
    health_tick_interval_seconds: int = 30
    health_stale_after_seconds: int = 60

    # Reserved for B4 (reliability recheck) and B5 (ingestion cycle).
    # Kept here so the env surface is stable across slices — operators
    # can already set ``CLAY_SCHEDULER_RELIABILITY_INTERVAL_SECONDS=120``
    # in dev and it will simply be picked up when B4 lands.
    reliability_recheck_interval_seconds: int = 300
    ingestion_cycle_interval_seconds: int = 60

    # 5b-ii.2b-ii: gate for the ``ai-agent-cycle`` job. ``False`` skips
    # registration (default ``False`` — opt-in only). The controlled
    # live-smoke (5b-iii) will flip it to ``True`` temporarily.
    ai_agent_enabled: bool = False

    # 5b-ii.2b-ii: interval for the ``ai-agent-cycle`` job. Default 300s
    # (5 minutes) is appropriate for a config-review agent; the live-smoke
    # will override to a shorter value for quick feedback.
    ai_agent_interval_seconds: int = 300

    # 5b-ii.2b-ii: role ids that the ``ai-agent-cycle`` job resolves
    # through ``ServiceModelResolver``. JSON list in env var, e.g.
    # ``CLAY_SCHEDULER_AI_AGENT_ROLE_IDS='["chief-agent","market-scanner"]'``.
    # Default = ``["chief-agent"]``.
    ai_agent_role_ids: list[str] = ["chief-agent"]

    # MP1: interval for the ``ops-retention`` prune-job. Default 86400s
    # (once per day). Operator can override via
    # ``CLAY_SCHEDULER_OPS_RETENTION_INTERVAL_SECONDS``.
    ops_retention_interval_seconds: int = 86400

    # S3d-2: gate for the ``provider-pool-reconcile`` job. ``False`` skips
    # registration (default ``False`` — opt-in only). S3d-3 will flip it ON.
    provider_pool_reconcile_enabled: bool = False

    # S3d-2: interval for the ``provider-pool-reconcile`` job. Default 300s
    # (5 minutes). Sync job on ThreadPoolExecutor.
    provider_pool_reconcile_interval_seconds: int = 300

    # MP2: readiness stale-threshold in seconds. Default 120 (2 × default
    # ingestion_cycle_interval). Used by ``/health/ready`` to classify
    # ingest-freshness as stale. Overridable via
    # ``CLAY_SCHEDULER_READINESS_STALE_THRESHOLD_SECONDS``.
    readiness_stale_threshold_seconds: int = 120

    @model_validator(mode="after")
    def _stale_after_at_least_two_ticks(self) -> SchedulerSettings:
        """Invariant from B2 (Emma carry-forward): ``stale_after`` must
        be at least ``2 * tick_interval`` so 2 missed ticks is the
        smallest granularity that classifies a service as STALE
        without false positives.
        """
        threshold = 2 * self.health_tick_interval_seconds
        if self.health_stale_after_seconds < threshold:
            raise ValueError(
                f"health_stale_after_seconds "
                f"({self.health_stale_after_seconds}) must be >= 2 * "
                f"health_tick_interval_seconds ({threshold})"
            )
        return self
