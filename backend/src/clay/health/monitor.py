from datetime import UTC, datetime, timedelta

from clay.services.models import ServiceStatus
from clay.services.registry import ServiceRegistry


class HealthMonitor:
    """Marks services stale when heartbeats stop arriving on time."""

    def __init__(
        self, registry: ServiceRegistry, stale_after_seconds: int = 60
    ) -> None:
        self.registry = registry
        self.stale_after = timedelta(seconds=stale_after_seconds)

    def refresh(self) -> None:
        now = datetime.now(UTC)
        for service in self.registry.list_services():
            if (
                service.last_heartbeat_at is not None
                and now - service.last_heartbeat_at > self.stale_after
            ):
                self.registry.update_status(service.service_id, ServiceStatus.STALE)
