import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from clay.api.dependencies import get_event_bus
from clay.events.bus import EventBus


router = APIRouter(prefix="/demo-trading", tags=["demo-trading"])

RELEVANT_EVENTS = {
    "demo.updated",
    "ingestion.updated",
    "session.updated",
    "signals.updated",
    "workspace.updated",
}


def encode_sse(event_type: str, payload: dict[str, object]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


async def demo_trading_event_lines(event_bus: EventBus) -> AsyncIterator[str]:
    queue = event_bus.subscribe()
    try:
        yield encode_sse("demo.ready", {"status": "connected"})
        while True:
            message = await queue.get()
            if message.event_type not in RELEVANT_EVENTS:
                continue
            yield encode_sse(
                "demo.refresh",
                {"upstream_event": message.event_type, "payload": message.payload},
            )
    finally:
        event_bus.unsubscribe(queue)


@router.get("/stream")
async def get_demo_trading_stream(
    event_bus: Annotated[EventBus, Depends(get_event_bus)],
) -> StreamingResponse:
    return StreamingResponse(
        demo_trading_event_lines(event_bus),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
