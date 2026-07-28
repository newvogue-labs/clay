from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from clay.bootstrap import event_bus
from clay.events.sse import sse_event_stream

router = APIRouter(prefix="/events", tags=["events"])


async def event_lines() -> AsyncIterator[str]:
    async for line in sse_event_stream(
        event_bus,
        ready_event="control.ready",
        relevant_events=None,
        refresh_event=None,
    ):
        yield line


@router.get("/stream")
async def get_event_stream() -> StreamingResponse:
    return StreamingResponse(
        event_lines(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
