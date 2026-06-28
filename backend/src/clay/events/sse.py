import asyncio
import json
from collections.abc import AsyncIterator

from clay.events.bus import EventBus


def encode_sse(event_type: str, payload: dict[str, object]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


async def sse_event_stream(
    event_bus: EventBus,
    *,
    ready_event: str,
    relevant_events: set[str] | None = None,
    refresh_event: str | None = None,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[str]:
    queue = event_bus.subscribe()
    try:
        yield encode_sse(ready_event, {"status": "connected"})
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue

            if (
                relevant_events is not None
                and message.event_type not in relevant_events
            ):
                continue

            if refresh_event is not None:
                yield encode_sse(
                    refresh_event,
                    {
                        "upstream_event": message.event_type,
                        "payload": message.payload,
                    },
                )
            else:
                yield encode_sse(message.event_type, message.payload)
    finally:
        event_bus.unsubscribe(queue)
