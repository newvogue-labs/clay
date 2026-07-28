from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from clay.api.dependencies import get_event_bus
from clay.events.bus import EventBus
from clay.events.sse import sse_event_stream

router = APIRouter(prefix="/control-center", tags=["control-center"])

RELEVANT_EVENTS = {
    "config.updated",
    "control.ready",
    "ingestion.updated",
    "runtime.updated",
    "service.updated",
}


async def control_center_event_lines(event_bus: EventBus) -> AsyncIterator[str]:
    async for line in sse_event_stream(
        event_bus,
        ready_event="control-center.ready",
        relevant_events=RELEVANT_EVENTS,
        refresh_event="control-center.refresh",
    ):
        yield line


@router.get("/stream")
async def get_control_center_stream(
    event_bus: Annotated[EventBus, Depends(get_event_bus)],
) -> StreamingResponse:
    return StreamingResponse(
        control_center_event_lines(event_bus),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
