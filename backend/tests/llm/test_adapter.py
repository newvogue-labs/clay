"""Offline stub smoke test for the LLM adapter (0 external egress)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from clay.llm import ChatCompletionRequest, ChatMessage, LLMAdapter
from clay.llm.adapter import _normalize_response
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


def test_normalize_response_null_content() -> None:
    raw = {
        "id": "test-1",
        "model": "gemma-4-31b",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "thinking about market conditions",
                },
                "finish_reason": "stop",
            }
        ],
    }
    result = _normalize_response(raw)
    assert result["choices"][0]["message"]["content"] == ""
    assert (
        result["choices"][0]["message"]["reasoning_content"]
        == "thinking about market conditions"
    )


def test_normalize_response_preserves_real_content() -> None:
    raw = {
        "id": "test-2",
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "real answer"},
                "finish_reason": "stop",
            }
        ],
    }
    result = _normalize_response(raw)
    assert result["choices"][0]["message"]["content"] == "real answer"


def test_normalize_response_null_reasoning() -> None:
    raw = {
        "id": "test-3",
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": None,
                },
                "finish_reason": "stop",
            }
        ],
    }
    result = _normalize_response(raw)
    assert result["choices"][0]["message"]["content"] == ""


def test_adapter_null_content_coerces_to_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "stub-null",
                "model": "gemma-4-31b",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "reasoning_content": "deep reasoning trace",
                        },
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
        model="gemma-4-31b",
        messages=[ChatMessage(role="user", content="ping")],
        max_tokens=5,
    )
    response = asyncio.run(adapter.chat_completion(request))

    assert response.choices[0].message.content == ""
    assert response.choices[0].message.reasoning_content == "deep reasoning trace"
