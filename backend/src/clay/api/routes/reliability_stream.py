from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from clay.api.dependencies import get_event_bus
from clay.events.bus import EventBus
from clay.events.sse import sse_event_stream

router = APIRouter(prefix="/reliability", tags=["reliability"])

RELEVANT_EVENTS = {
    "runtime.updated",
    "ingestion.updated",
    "ai.updated",
    "demo.updated",
    "review.updated",
    "validation.updated",
    "session.updated",
    "config.updated",
    "reliability.updated",
}


async def reliability_event_lines(event_bus: EventBus) -> AsyncIterator[str]:
    async for line in sse_event_stream(
        event_bus,
        ready_event="reliability.ready",
        relevant_events=RELEVANT_EVENTS,
        refresh_event="reliability.refresh",
    ):
        yield line


@router.get("/stream")
async def get_reliability_stream(
    event_bus: Annotated[EventBus, Depends(get_event_bus)],
) -> StreamingResponse:
    return StreamingResponse(
        reliability_event_lines(event_bus),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
