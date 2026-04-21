import asyncio

from clay.api.routes.session_review_stream import session_review_event_lines
from clay.events.bus import EventBus


def test_session_review_stream_emits_refresh_for_review_events() -> None:
    async def scenario() -> tuple[str, str]:
        event_bus = EventBus()
        stream = session_review_event_lines(event_bus)
        ready_event = await anext(stream)
        event_bus.publish("review.updated", {"event_type": "review.feedback.captured"})
        refresh_event = await anext(stream)
        await stream.aclose()
        return ready_event, refresh_event

    ready_event, refresh_event = asyncio.run(scenario())

    assert "session-review.ready" in ready_event
    assert "session-review.refresh" in refresh_event
    assert "review.updated" in refresh_event
