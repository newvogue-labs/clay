import asyncio
from collections.abc import AsyncGenerator
from typing import cast

from clay.api.routes.demo_trading_stream import demo_trading_event_lines
from clay.events.bus import EventBus


def test_demo_trading_stream_emits_refresh_for_demo_events() -> None:
    async def scenario() -> tuple[str, str]:
        event_bus = EventBus()
        stream = cast(AsyncGenerator[str, None], demo_trading_event_lines(event_bus))
        ready_event = await anext(stream)
        event_bus.publish("demo.updated", {"event_type": "demo.trade.logged"})
        refresh_event = await anext(stream)
        await stream.aclose()
        return ready_event, refresh_event

    ready_event, refresh_event = asyncio.run(scenario())

    assert "demo.ready" in ready_event
    assert "demo.refresh" in refresh_event
    assert "demo.updated" in refresh_event
