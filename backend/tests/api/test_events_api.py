from collections.abc import AsyncGenerator
from typing import cast

import pytest

from clay.api.routes.events import get_event_stream


@pytest.mark.anyio
async def test_events_stream_returns_sse_response() -> None:
    response = await get_event_stream()

    assert response.headers["content-type"].startswith("text/event-stream")

    stream = cast(AsyncGenerator[str, None], response.body_iterator)
    first_chunk = await anext(stream)
    assert first_chunk == 'event: control.ready\ndata: {"status": "connected"}\n\n'

    await stream.aclose()
