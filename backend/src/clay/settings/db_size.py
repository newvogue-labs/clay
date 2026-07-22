"""DbSizeMonitorSettings — advisory DB-size monitor thresholds.

D-13 slice #1: two-band (warning / critical) advisory monitor for the
total database size.  **default-OFF** — ``pg_database_size`` is never
called when ``monitor_enabled`` is ``False``.

Read at the composition boundary (``build_services`` in
``clay.bootstrap``) and passed into ``ReliabilityService`` via DI —
the A6 contract: the service never imports ``settings/*`` directly.

Env prefix: ``CLAY_DB_SIZE_`` (e.g. ``CLAY_DB_SIZE_MONITOR_ENABLED``).
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DbSizeMonitorSettings(BaseSettings):
    """Advisory DB-size monitor configuration.

    * ``monitor_enabled`` — flag-gate.  ``False`` (default) means
      ``pg_database_size`` is never called and the reliability
      snapshot is byte-identical to the pre-D-13 version.
    * ``warning_bytes`` — size that triggers the ``db-size-warning``
      advisory band (severity ``warning``, no audit emission).
      Default 5 GiB (5_368_709_120).  Env:
      ``CLAY_DB_SIZE_WARNING_BYTES``.
    * ``critical_bytes`` — size that triggers the ``db-size-critical``
      advisory band (severity ``critical``, flips ``overall_status``
      to ``degraded`` and emits audit on first transition).  Default
      10 GiB (10_737_418_240).  Env:
      ``CLAY_DB_SIZE_CRITICAL_BYTES``.
    """

    model_config = SettingsConfigDict(
        env_prefix="CLAY_DB_SIZE_",
        extra="ignore",
    )

    monitor_enabled: bool = False
    warning_bytes: int = 5_368_709_120  # 5 GiB
    critical_bytes: int = 10_737_418_240  # 10 GiB

    @model_validator(mode="after")
    def _critical_gt_warning_gt_zero(self) -> DbSizeMonitorSettings:
        """Invariant: ``critical_bytes > warning_bytes > 0``."""
        if self.warning_bytes <= 0:
            raise ValueError(f"warning_bytes ({self.warning_bytes}) must be > 0")
        if self.critical_bytes <= self.warning_bytes:
            raise ValueError(
                f"critical_bytes ({self.critical_bytes}) must be > "
                f"warning_bytes ({self.warning_bytes})"
            )
        return self
