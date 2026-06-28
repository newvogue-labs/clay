import asyncio
from collections.abc import AsyncGenerator
from typing import cast

from clay.api.routes.control_center_stream import control_center_event_lines
from clay.events.bus import EventBus


def test_control_center_stream_emits_refresh_for_relevant_events() -> None:
    async def scenario() -> tuple[str, str]:
        event_bus = EventBus()
        stream = cast(AsyncGenerator[str, None], control_center_event_lines(event_bus))
        ready_event = await anext(stream)
        event_bus.publish("ingestion.updated", {"market_records_written": 4})
        refresh_event = await anext(stream)
        await stream.aclose()
        return ready_event, refresh_event

    ready_event, refresh_event = asyncio.run(scenario())

    assert "control-center.ready" in ready_event
    assert "control-center.refresh" in refresh_event
    assert "ingestion.updated" in refresh_event
