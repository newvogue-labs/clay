from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from clay.bootstrap import audit_writer, event_bus, runtime_manager
from clay.runtime.states import RuntimeState

router = APIRouter(prefix="/runtime", tags=["runtime"])


class RuntimeTransitionRequest(BaseModel):
    target: RuntimeState


@router.get("/state")
async def get_runtime_state() -> dict[str, object]:
    return runtime_manager.snapshot().model_dump(mode="json")


@router.post("/transition")
async def transition_runtime(payload: RuntimeTransitionRequest) -> dict[str, object]:
    try:
        runtime_manager.transition_to(payload.target)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    audit_writer.write(
        "runtime.transitioned",
        {"target": payload.target.value},
    )
    event_bus.publish(
        "runtime.updated",
        runtime_manager.snapshot().model_dump(mode="json"),
    )
    return runtime_manager.snapshot().model_dump(mode="json")
