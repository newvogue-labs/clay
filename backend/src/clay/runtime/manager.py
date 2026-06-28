from clay.runtime.states import RuntimeSnapshot, RuntimeState
from clay.runtime.transitions import get_allowed_transitions, validate_transition
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry


# States that ``reconcile_to`` is allowed to project the runtime into.
# These are the *only* states a restored ``session_state`` row can map
# to (see ``SessionControlService.reconcile_runtime_state``):
# - ACTIVE_SESSION: a session was running before restart (``paused_at IS NULL``);
# - PAUSED: a session was paused before restart (``paused_at`` set).
# Whitelisting matters: ``reconcile_to`` skips ``validate_transition`` and
# ``_assert_critical_services_ready`` (reconcile = fact, not request), so we
# must not let it become a back-door setter for arbitrary states (e.g.
# BACKGROUND_MONITORING, REVIEW, DEGRADED — those have no "restored" analogue).
_RECONCILABLE_STATES: frozenset[RuntimeState] = frozenset(
    {RuntimeState.ACTIVE_SESSION, RuntimeState.PAUSED}
)


class RuntimeManager:
    """Owns the current runtime snapshot for the local control plane."""

    def __init__(
        self,
        initial_state: RuntimeState = RuntimeState.BACKGROUND_MONITORING,
        registry: ServiceRegistry | None = None,
    ) -> None:
        self._state = initial_state
        self.registry = registry or ServiceRegistry()

    def snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            state=self._state,
            allowed_transitions=get_allowed_transitions(self._state),
        )

    @property
    def state(self) -> RuntimeState:
        return self._state

    def transition_to(self, target: RuntimeState) -> RuntimeState:
        validate_transition(self._state, target)
        if target is RuntimeState.PRE_SESSION:
            self._assert_critical_services_ready()
        self._state = target
        return self._state

    def reconcile_to(self, target: RuntimeState) -> RuntimeState:
        """Project the runtime state to a value restored from persisted
        source-of-truth (e.g. ``session_state.session_id`` + ``paused_at``).

        **Boot-safety by design:** unlike ``transition_to``, this method
        does NOT call ``validate_transition`` (no path validation) and
        does NOT call ``_assert_critical_services_ready`` (no readiness
        gate). The argument is that a reconciled state is a *fact* — we
        just read it from the DB on startup — not a *request* to change
        mode. A healthy system must be able to come back up with a
        previously-active session even if the control-api service has
        not yet reported HEALTHY (A6: closing the post-restart
        ``lifecycle_state="review"`` trap from A4 §6 Q2).

        **Whitelist guard:** only ``ACTIVE_SESSION`` and ``PAUSED`` are
        valid reconcile targets. These are the two states a restored
        ``_active_session`` can project to. ``BACKGROUND_MONITORING``
        (no session restored) and ``REVIEW`` (post-complete) are NOT
        restored — they are reached via ``transition_to`` (operator
        action) or by leaving the manager at its default. ``DEGRADED``
        is reached via ``enter_degraded`` (service health axis — a
        separate concern owned by the runtime-health monitor in
        Wave B / ADR-007; this method never touches it).

        The whitelist is what keeps the relaxed validation honest: we
        skip path/readiness checks (reconcile is a fact, not a request)
        but we still validate that the target is *reconcile-valid*
        (you cannot use this to set ``DEGRADED`` or ``BACKGROUND_MONITORING``).
        """
        if target not in _RECONCILABLE_STATES:
            raise ValueError(
                f"reconcile_to accepts only restore states "
                f"{sorted(s.value for s in _RECONCILABLE_STATES)}, got {target.value!r}"
            )
        self._state = target
        return self._state

    def enter_degraded(self) -> RuntimeState:
        self._state = RuntimeState.DEGRADED
        return self._state

    def _assert_critical_services_ready(self) -> None:
        for service in self.registry.list_services():
            if (
                service.criticality is ServiceCriticality.CRITICAL
                and service.status
                not in {ServiceStatus.HEALTHY, ServiceStatus.DEGRADED}
            ):
                raise RuntimeError(
                    f"critical service {service.service_id} is not ready"
                )
