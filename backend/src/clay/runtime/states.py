from enum import StrEnum

from pydantic import BaseModel


class RuntimeState(StrEnum):
    BACKGROUND_MONITORING = "background_monitoring"
    PRE_SESSION = "pre_session"
    ACTIVE_SESSION = "active_session"
    PAUSED = "paused"
    REVIEW = "review"
    DEGRADED = "degraded"


class RuntimeSnapshot(BaseModel):
    state: RuntimeState
    allowed_transitions: list[RuntimeState]
