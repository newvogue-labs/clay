"""Offline tests for AgentRunner (DEPLOY-5 / 5b-ii.1).

Mirrors tests/llm/test_adapter.py: synchronous test functions driving async
code via asyncio.run(), with httpx.MockTransport for the Ollama client.
No network, no DB, no gateway.
"""

from __future__ import annotations

import asyncio

import httpx

from clay.ai_control.runner import (
    AgentRunner,
    ModelResponse,
    OllamaNativeClient,
)
from clay.llm import ChatMessage

class StubResolver:
    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def resolve_model_id(self, role_id: str) -> str:
        return self._mapping.get(role_id, "")

class RecordingClient:
    """Minimal ModelClient capturing the call and returning a canned reply."""

    def __init__(self, response: ModelResponse) -> None:
        self._response = response
        self.calls: list[dict] = []

    async def chat(self, messages, *, model, think=True, num_predict=None):
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "think": think,
                "num_predict": num_predict,
            }
        )
        return self._response

def test_run_agent_resolves_model_and_returns_content() -> None:
    client = RecordingClient(
        ModelResponse(content="QUASAR-7741", thinking=None, model="gemma4-e2b")
    )
    runner = AgentRunner(
        model_resolver=StubResolver({"signal": "gemma4:e2b-it-qat"}),
        model_client=client,
        role_prompts={"signal": "You are the signal agent."},
    )

    result = asyncio.run(runner.run_agent("signal", "What is the launch code?"))

    assert result.role_id == "signal"
    assert result.model_id == "gemma4:e2b-it-qat"
    assert result.content == "QUASAR-7741"
    assert result.thinking is None
    # governance not duplicated: model id came straight from the resolver
    assert client.calls[0]["model"] == "gemma4:e2b-it-qat"
    assert client.calls[0]["think"] is True
    # system prompt + user context assembled in order
    assert [m.role for m in result.messages] == ["system", "user"]
    assert result.messages[0].content == "You are the signal agent."
    assert result.messages[1].content == "What is the launch code?"

def test_run_agent_captures_thinking_when_present() -> None:
    client = RecordingClient(
        ModelResponse(content="42", thinking="let me reason...", model="m")
    )
    runner = AgentRunner(
        model_resolver=StubResolver({"r": "m"}),
        model_client=client,
    )

    result = asyncio.run(runner.run_agent("r", "ctx"))

    assert result.content == "42"
    assert result.thinking == "let me reason..."

def test_run_agent_rejects_unassigned_role() -> None:
    runner = AgentRunner(
        model_resolver=StubResolver({}),
        model_client=RecordingClient(ModelResponse(content="x")),
    )
    raised = False
    try:
        asyncio.run(runner.run_agent("missing", "ctx"))
    except ValueError:
        raised = True
    assert raised

def test_ollama_native_client_parses_thinking_and_content() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gemma4:e2b-it-qat",
                "message": {
                    "role": "assistant",
                    "thinking": "reasoning trace",
                    "content": "QUASAR-7741",
                },
                "done": True,
            },
        )

    client = OllamaNativeClient(transport=httpx.MockTransport(handler))
    resp = asyncio.run(
        client.chat(
            [ChatMessage(role="user", content="code?")],
            model="gemma4:e2b-it-qat",
            think=True,
            num_predict=256,
        )
    )

    assert resp.content == "QUASAR-7741"
    assert resp.thinking == "reasoning trace"
    assert resp.model == "gemma4:e2b-it-qat"
    # native endpoint (NOT /v1), with think + num_ctx options
    assert captured["url"].endswith("/api/chat")
    assert captured["body"]["think"] is True
    assert captured["body"]["stream"] is False
    assert captured["body"]["options"]["num_ctx"] == 65536
    assert captured["body"]["options"]["num_predict"] == 256
    assert captured["body"]["messages"][0] == {"role": "user", "content": "code?"}

def test_ollama_native_client_empty_thinking_is_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "m",
                "message": {"role": "assistant", "content": "ok", "thinking": ""},
            },
        )

    client = OllamaNativeClient(transport=httpx.MockTransport(handler))
    resp = asyncio.run(
        client.chat([ChatMessage(role="user", content="hi")], model="m")
    )
    assert resp.content == "ok"
    assert resp.thinking is None
