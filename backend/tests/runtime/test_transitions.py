import pytest

from clay.runtime.manager import RuntimeManager
from clay.runtime.states import RuntimeState
from clay.runtime.transitions import (
    InvalidTransitionError,
    get_allowed_transitions,
    validate_transition,
)
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry


def test_background_monitoring_allows_pre_session() -> None:
    assert RuntimeState.PRE_SESSION in get_allowed_transitions(
        RuntimeState.BACKGROUND_MONITORING,
    )


def test_background_monitoring_rejects_active_session() -> None:
    with pytest.raises(InvalidTransitionError):
        validate_transition(
            RuntimeState.BACKGROUND_MONITORING,
            RuntimeState.ACTIVE_SESSION,
        )


def test_paused_allows_return_to_active_session() -> None:
    validate_transition(RuntimeState.PAUSED, RuntimeState.ACTIVE_SESSION)


def test_runtime_manager_can_enter_pre_session_when_critical_services_are_healthy() -> (
    None
):
    registry = ServiceRegistry()
    registry.register("control-api", "api", ServiceCriticality.CRITICAL, "always-on")
    registry.update_status("control-api", ServiceStatus.HEALTHY)
    manager = RuntimeManager(registry=registry)

    manager.transition_to(RuntimeState.PRE_SESSION)

    assert manager.state is RuntimeState.PRE_SESSION


def test_runtime_manager_rejects_pre_session_when_critical_service_is_not_ready() -> (
    None
):
    registry = ServiceRegistry()
    registry.register("control-api", "api", ServiceCriticality.CRITICAL, "always-on")
    manager = RuntimeManager(registry=registry)

    with pytest.raises(RuntimeError):
        manager.transition_to(RuntimeState.PRE_SESSION)
