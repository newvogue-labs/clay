import asyncio

from clay.api.routes.session_stream import session_event_lines
from clay.events.bus import EventBus


def test_session_stream_emits_refresh_for_session_events() -> None:
    async def scenario() -> tuple[str, str]:
        event_bus = EventBus()
        stream = session_event_lines(event_bus)
        ready_event = await anext(stream)
        event_bus.publish("session.updated", {"event_type": "session.started"})
        refresh_event = await anext(stream)
        await stream.aclose()
        return ready_event, refresh_event

    ready_event, refresh_event = asyncio.run(scenario())

    assert "session.ready" in ready_event
    assert "session.refresh" in refresh_event
    assert "session.updated" in refresh_event
