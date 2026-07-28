from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from clay.api.dependencies import get_event_bus
from clay.events.bus import EventBus
from clay.events.sse import sse_event_stream

router = APIRouter(prefix="/validation-lab", tags=["validation-lab"])

RELEVANT_EVENTS = {
    "validation.updated",
    "review.updated",
    "knowledge.updated",
}


async def validation_lab_event_lines(event_bus: EventBus) -> AsyncIterator[str]:
    async for line in sse_event_stream(
        event_bus,
        ready_event="validation-lab.ready",
        relevant_events=RELEVANT_EVENTS,
        refresh_event="validation-lab.refresh",
    ):
        yield line


@router.get("/stream")
async def get_validation_lab_stream(
    event_bus: Annotated[EventBus, Depends(get_event_bus)],
) -> StreamingResponse:
    return StreamingResponse(
        validation_lab_event_lines(event_bus),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
