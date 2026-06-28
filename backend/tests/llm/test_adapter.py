"""Offline stub smoke test for the LLM adapter (0 external egress)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from clay.llm import ChatCompletionRequest, ChatMessage, LLMAdapter
from clay.settings.llm import LLMSettings


def test_llm_adapter_chat_completion_stub() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "stub-1",
                "model": "stub-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "pong"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    adapter = LLMAdapter(
        settings=LLMSettings(base_url="http://stub.local"),
        transport=httpx.MockTransport(handler),
    )
    request = ChatCompletionRequest(
        model="stub-model",
        messages=[ChatMessage(role="user", content="ping")],
    )
    response = asyncio.run(adapter.chat_completion(request))

    assert response.choices[0].message.content == "pong"
    assert captured["url"] == "http://stub.local/v1/chat/completions"
    assert captured["body"]["model"] == "stub-model"
