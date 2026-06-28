import asyncio
from collections.abc import AsyncGenerator
from typing import cast

from clay.api.routes.knowledge_stream import knowledge_event_lines
from clay.events.bus import EventBus


def test_knowledge_stream_emits_refresh_for_knowledge_events() -> None:
    async def scenario() -> tuple[str, str]:
        event_bus = EventBus()
        stream = cast(AsyncGenerator[str, None], knowledge_event_lines(event_bus))
        ready_event = await anext(stream)
        event_bus.publish("knowledge.updated", {"event_type": "knowledge.item.created"})
        refresh_event = await anext(stream)
        await stream.aclose()
        return ready_event, refresh_event

    ready_event, refresh_event = asyncio.run(scenario())

    assert "knowledge.ready" in ready_event
    assert "knowledge.refresh" in refresh_event
    assert "knowledge.updated" in refresh_event
