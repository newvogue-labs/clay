import asyncio

from clay.api.routes.validation_lab_stream import validation_lab_event_lines
from clay.events.bus import EventBus


def test_validation_lab_stream_emits_refresh_for_validation_events() -> None:
    async def scenario() -> tuple[str, str]:
        event_bus = EventBus()
        stream = validation_lab_event_lines(event_bus)
        ready_event = await anext(stream)
        event_bus.publish(
            "validation.updated", {"event_type": "validation.run.completed"}
        )
        refresh_event = await anext(stream)
        await stream.aclose()
        return ready_event, refresh_event

    ready_event, refresh_event = asyncio.run(scenario())

    assert "validation-lab.ready" in ready_event
    assert "validation-lab.refresh" in refresh_event
    assert "validation.updated" in refresh_event
