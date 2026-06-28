import asyncio
from collections.abc import AsyncGenerator
from typing import cast

from clay.api.routes.reliability_stream import reliability_event_lines
from clay.events.bus import EventBus


def test_reliability_stream_emits_refresh_for_runtime_updates() -> None:
    async def scenario() -> tuple[str, str]:
        event_bus = EventBus()
        stream = cast(AsyncGenerator[str, None], reliability_event_lines(event_bus))
        ready_event = await anext(stream)
        event_bus.publish("runtime.updated", {"state": "degraded"})
        refresh_event = await anext(stream)
        await stream.aclose()
        return ready_event, refresh_event

    ready_event, refresh_event = asyncio.run(scenario())

    assert "reliability.ready" in ready_event
    assert "reliability.refresh" in refresh_event
    assert "runtime.updated" in refresh_event
