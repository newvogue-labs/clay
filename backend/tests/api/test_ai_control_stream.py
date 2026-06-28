import asyncio
from collections.abc import AsyncGenerator
from typing import cast

from clay.api.routes.ai_control_stream import ai_control_event_lines
from clay.events.bus import EventBus


def test_ai_control_stream_emits_refresh_on_ai_events() -> None:
    async def scenario() -> tuple[str, str]:
        event_bus = EventBus()
        stream = cast(AsyncGenerator[str, None], ai_control_event_lines(event_bus))
        ready_event = await anext(stream)
        event_bus.publish("ai.updated", {"role_id": "forecast-model"})
        refresh_event = await anext(stream)
        await stream.aclose()
        return ready_event, refresh_event

    ready_event, refresh_event = asyncio.run(scenario())

    assert "ai-control.ready" in ready_event
    assert "ai-control.refresh" in refresh_event
    assert "ai.updated" in refresh_event
