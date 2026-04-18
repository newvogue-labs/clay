import asyncio

from clay.api.routes.workspace_stream import workspace_event_lines
from clay.events.bus import EventBus


def test_workspace_stream_emits_refresh_for_focus_and_ingestion_events() -> None:
    async def scenario() -> tuple[str, str]:
        event_bus = EventBus()
        stream = workspace_event_lines(event_bus)
        ready_event = await anext(stream)
        event_bus.publish("workspace.updated", {"symbol": "BTCUSDT"})
        refresh_event = await anext(stream)
        await stream.aclose()
        return ready_event, refresh_event

    ready_event, refresh_event = asyncio.run(scenario())

    assert "workspace.ready" in ready_event
    assert "workspace.refresh" in refresh_event
    assert "workspace.updated" in refresh_event
