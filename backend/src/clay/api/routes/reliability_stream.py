import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from clay.api.dependencies import get_event_bus
from clay.events.bus import EventBus


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


def encode_sse(event_type: str, payload: dict[str, object]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


async def reliability_event_lines(event_bus: EventBus) -> AsyncIterator[str]:
    queue = event_bus.subscribe()
    try:
        yield encode_sse("reliability.ready", {"status": "connected"})
        while True:
            message = await queue.get()
            if message.event_type not in RELEVANT_EVENTS:
                continue
            yield encode_sse(
                "reliability.refresh",
                {"upstream_event": message.event_type, "payload": message.payload},
            )
    finally:
        event_bus.unsubscribe(queue)


@router.get("/stream")
async def get_reliability_stream(
    event_bus: Annotated[EventBus, Depends(get_event_bus)],
) -> StreamingResponse:
    return StreamingResponse(
        reliability_event_lines(event_bus),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
