from datetime import UTC, datetime

from sqlalchemy.orm import Session

from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.control_center.models import (
    ActiveConfigurationSnapshot,
    AuditEventSnapshot,
    ConfigScopeSnapshot,
    ConnectorStatusSnapshot,
    ControlCenterSnapshot,
    GlobalHealthSummary,
    IncidentSnapshot,
    IngestionHealthSnapshot,
    MarketFreshnessItem,
    RuntimeStatusSnapshot,
    ServiceCardSnapshot,
)
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.freshness.evaluator import (
    collapse_market_statuses,
    evaluate_context_freshness,
    resolve_market_freshness_status,
)
from clay.preflight.models import PreflightResult
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.settings.ingestion import IngestionSettings
from clay.runtime.states import RuntimeState
from clay.services.registry import ServiceRegistry
from clay.services.supervisor import ProcessSupervisor


STATUS_PRIORITY = {
    "fresh": 0,
    "healthy": 0,
    "unknown": 1,
    "degraded": 2,
    "stale": 3,
    "error": 4,
}


class ControlCenterService:
    def __init__(
        self,
        *,
        runtime_manager: RuntimeManager,
        preflight_service: PreflightService,
        registry: ServiceRegistry,
        supervisor: ProcessSupervisor,
        config_loader: ConfigLoader,
        audit_writer: AuditWriter,
        ingestion_settings: IngestionSettings,
    ) -> None:
        self.runtime_manager = runtime_manager
        self.preflight_service = preflight_service
        self.registry = registry
        self.supervisor = supervisor
        self.config_loader = config_loader
        self.audit_writer = audit_writer
        self.ingestion_settings = ingestion_settings

    def build_snapshot(self, session: Session) -> ControlCenterSnapshot:
        now = datetime.now(UTC)
        preflight = self.preflight_service.run()
        runtime = self._build_runtime_snapshot(preflight)
        services = self._build_service_cards()
        ingestion = self._build_ingestion_snapshot(session, now=now)
        incidents = self._build_incidents(session)

        return ControlCenterSnapshot(
            summary=self._build_summary(
                now=now,
                runtime=runtime,
                services=services,
                ingestion=ingestion,
                incidents=incidents,
                preflight=preflight,
            ),
            runtime=runtime,
            services=services,
            ingestion=ingestion,
            incidents=incidents,
            audit=self._read_audit_events(limit=12),
            config=self._build_config_snapshot(),
        )

    def _build_runtime_snapshot(
        self,
        preflight: PreflightResult,
    ) -> RuntimeStatusSnapshot:
        runtime_snapshot = self.runtime_manager.snapshot()
        blocking_reason: str | None = None
        if preflight.status == "hard_fail":
            failed_check = next(
                (
                    check
                    for check in preflight.checks
                    if check.status == "hard_fail"
                ),
                None,
            )
            blocking_reason = (
                f"preflight blocked by {failed_check.service_id}"
                if failed_check is not None
                else "preflight checks failed"
            )

        return RuntimeStatusSnapshot(
            state=runtime_snapshot.state.value,
            allowed_transitions=[item.value for item in runtime_snapshot.allowed_transitions],
            preflight_status=preflight.status,
            blocking_reason=blocking_reason,
        )

    def _build_service_cards(self) -> list[ServiceCardSnapshot]:
        return [
            ServiceCardSnapshot(
                service_id=service.service_id,
                service_name=service.service_id.replace("-", " ").title(),
                service_kind=service.service_type,
                lifecycle_class=service.startup_policy,
                criticality=service.criticality.value,
                status=service.status.value,
                last_heartbeat_at=(
                    service.last_heartbeat_at.isoformat()
                    if service.last_heartbeat_at is not None
                    else None
                ),
                last_error=service.last_error,
                freshness_status=None,
                allowed_actions=list(self.supervisor.allowed_actions(service.service_id)),
            )
            for service in self.registry.list_services()
        ]

    def _build_ingestion_snapshot(
        self,
        session: Session,
        *,
        now: datetime,
    ) -> IngestionHealthSnapshot:
        market_repo = MarketRepository(session)
        context_repo = ContextRepository(session)
        ops_repo = OpsRepository(session)

        market_thresholds = self.ingestion_settings.market_freshness_thresholds()
        context_thresholds = self.ingestion_settings.context_freshness_thresholds()

        market_items: list[MarketFreshnessItem] = []
        market_statuses: list[str] = []
        blocks_active_trading = False

        for row in market_repo.list_freshness_statuses():
            effective = resolve_market_freshness_status(
                stored_status=row.freshness_state,
                timeframe=row.timeframe,
                latest_bar_open_time=row.latest_bar_open_time,
                now=now,
                market_thresholds=market_thresholds,
            )
            market_items.append(
                MarketFreshnessItem(
                    symbol=row.symbol,
                    timeframe=row.timeframe,
                    status=effective.status,
                    evaluated_at=effective.observed_at.isoformat(),
                    latest_bar_open_time=(
                        row.latest_bar_open_time.isoformat()
                        if row.latest_bar_open_time is not None
                        else None
                    ),
                    reason=effective.reason,
                ),
            )
            market_statuses.append(effective.status)
            if effective.blocks_active_trading:
                blocks_active_trading = True

        latest_news = context_repo.latest_news(limit=1)
        latest_sentiment = context_repo.latest_sentiment(limit=1)
        news_freshness = evaluate_context_freshness(
            stream_name="news",
            last_received_at=latest_news[0].published_at if latest_news else None,
            now=now,
            context_thresholds=context_thresholds,
        )
        sentiment_freshness = evaluate_context_freshness(
            stream_name="sentiment",
            last_received_at=latest_sentiment[0].captured_at if latest_sentiment else None,
            now=now,
            context_thresholds=context_thresholds,
        )

        connector_rows = ops_repo.latest_connector_statuses()
        context_status = "fresh"
        if (
            news_freshness.status != "fresh"
            or sentiment_freshness.status != "fresh"
            or any(row.status in {"degraded", "error"} for row in connector_rows)
        ):
            context_status = "degraded"

        return IngestionHealthSnapshot(
            market_status=collapse_market_statuses(market_statuses),
            context_status=context_status,
            blocks_active_trading=blocks_active_trading,
            market_items=market_items,
            connectors=[
                ConnectorStatusSnapshot(
                    connector_id=row.connector_id,
                    connector_type=row.connector_type,
                    status=row.status,
                    observed_at=row.observed_at.isoformat(),
                )
                for row in connector_rows
            ],
        )

    def _build_incidents(self, session: Session) -> list[IncidentSnapshot]:
        ops_repo = OpsRepository(session)
        return [
            IncidentSnapshot(
                source_name=row.source_name,
                severity=row.severity,
                lifecycle_status=row.lifecycle_status,
                message=row.message,
                recorded_at=row.recorded_at.isoformat(),
                resolved_at=row.resolved_at.isoformat() if row.resolved_at is not None else None,
                resolution_message=row.resolution_message,
            )
            for row in ops_repo.latest_incidents(limit=10, active_only=True)
        ]

    def _read_audit_events(self, *, limit: int) -> list[AuditEventSnapshot]:
        events_raw = self.audit_writer.read_recent(limit=limit)
        return [
            AuditEventSnapshot(
                timestamp=ev["timestamp"],
                event_type=ev["event_type"],
                payload=ev["payload"],
            )
            for ev in events_raw
        ]

    def _build_config_snapshot(self) -> ActiveConfigurationSnapshot:
        snapshot = self.config_loader.snapshot()
        mutable_scopes = set(self.config_loader.list_scopes())
        return ActiveConfigurationSnapshot(
            config_dir=str(self.config_loader.paths.config_dir),
            scopes=[
                ConfigScopeSnapshot(
                    scope=scope,
                    mutable=scope in mutable_scopes,
                    values=values,
                )
                for scope, values in snapshot.items()
            ],
        )

    def _build_summary(
        self,
        *,
        now: datetime,
        runtime: RuntimeStatusSnapshot,
        services: list[ServiceCardSnapshot],
        ingestion: IngestionHealthSnapshot,
        incidents: list[IncidentSnapshot],
        preflight: PreflightResult,
    ) -> GlobalHealthSummary:
        blocking_reason = runtime.blocking_reason
        if blocking_reason is None and ingestion.blocks_active_trading:
            blocking_reason = "market data freshness blocks active trading"

        critical_incidents = sum(
            1
            for incident in incidents
            if incident.severity in {"critical", "error"}
        )
        service_degradation = any(
            service.status in {"degraded", "stale", "error"}
            or (
                service.status == "stopped"
                and service.criticality != "optional"
            )
            for service in services
        )
        ingestion_degradation = (
            ingestion.market_status != "fresh"
            or ingestion.context_status != "fresh"
        )

        overall_status = "healthy"
        if (
            runtime.state == RuntimeState.DEGRADED.value
            or preflight.status == "hard_fail"
            or service_degradation
            or ingestion_degradation
            or incidents
        ):
            overall_status = "degraded"

        actionability = "normal"
        if preflight.status == "hard_fail" or ingestion.blocks_active_trading:
            actionability = "blocked"
        elif overall_status != "healthy":
            actionability = "limited"

        return GlobalHealthSummary(
            runtime_state=runtime.state,
            overall_status=overall_status,
            actionability=actionability,
            active_incident_count=len(incidents),
            critical_incident_count=critical_incidents,
            last_status_refresh_at=now.isoformat(),
            blocking_reason=blocking_reason,
        )

    def _is_worse_status(self, candidate: str, current: str) -> bool:
        return STATUS_PRIORITY.get(candidate, 99) > STATUS_PRIORITY.get(current, -1)
