import asyncio

from clay.ai_control.models import AssignmentApplyCommand, AssignmentReviewCommand
from clay.ai_control.service import AIControlService
from clay.api.routes.ai_control import (
    apply_ai_assignment,
    get_ai_control_overview,
    review_ai_assignment,
)
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry


def build_ai_service() -> AIControlService:
    registry = ServiceRegistry()
    registry.register(
        service_id="control-api",
        service_type="api",
        criticality=ServiceCriticality.CRITICAL,
        startup_policy="always-on",
    )
    registry.update_status("control-api", ServiceStatus.HEALTHY)

    config_loader = ConfigLoader()
    config_loader.ensure_default_configs()
    config_loader.load_all()

    return AIControlService(
        runtime_manager=RuntimeManager(registry=registry),
        preflight_service=PreflightService(registry),
        config_loader=config_loader,
        audit_writer=AuditWriter(config_loader.paths.state_dir),
        event_bus=EventBus(),
    )


def test_ai_control_overview_exposes_assignments(db_session) -> None:
    payload = asyncio.run(get_ai_control_overview(db_session, build_ai_service()))

    assert payload["summary"]["chief_agent_model"] == "MiniMax-M3"
    assert any(item["role_id"] == "chief-agent" for item in payload["assignments"])


def test_ai_control_review_and_apply_flow(db_session) -> None:
    service = build_ai_service()
    review_payload = asyncio.run(
        review_ai_assignment(
            command=AssignmentReviewCommand(
                role_id="forecast-model",
                model_id="forecast-lite-v1",
            ),
            session=db_session,
            service=service,
        )
    )
    assert review_payload["proposed_model_id"] == "forecast-lite-v1"

    apply_payload = asyncio.run(
        apply_ai_assignment(
            command=AssignmentApplyCommand(review_id=review_payload["review_id"]),
            session=db_session,
            service=service,
        )
    )
    assert any(
        row["role_id"] == "forecast-model" and row["model_id"] == "forecast-lite-v1"
        for row in apply_payload["assignments"]
    )
