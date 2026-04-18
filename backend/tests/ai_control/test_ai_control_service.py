from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.runtime.states import RuntimeState
from clay.services.registry import ServiceRegistry


def build_service() -> AIControlService:
    registry = ServiceRegistry()
    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)
    config_loader = ConfigLoader()
    config_loader.ensure_default_configs()
    config_loader.load_all()
    return AIControlService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        audit_writer=AuditWriter(config_loader.paths.state_dir),
        event_bus=EventBus(),
    )


def test_review_and_apply_assignment_changes_snapshot() -> None:
    service = build_service()

    review = service.review_assignment("forecast-model", "forecast-lite-v1")
    assert review.role_id == "forecast-model"
    assert review.proposed_model_id == "forecast-lite-v1"
    assert review.blocks_apply is False

    snapshot = service.apply_assignment(review.review_id)
    forecast_row = next(row for row in snapshot.assignments if row.role_id == "forecast-model")
    assert forecast_row.model_id == "forecast-lite-v1"


def test_active_session_marks_review_as_critical() -> None:
    service = build_service()
    service.runtime_manager.transition_to(RuntimeState.PRE_SESSION)
    service.runtime_manager.transition_to(RuntimeState.ACTIVE_SESSION)

    review = service.review_assignment("chief-agent", "anthropic-claude-sonnet-4.5")
    assert review.severity == "critical"
    assert review.approval_required is True
