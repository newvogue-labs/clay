"""Offline tests for AgentRunner + transport (DEPLOY-5 / 5b-ii.1 + 5b-ii.2a).

Mirrors tests/llm/test_adapter.py: synchronous functions driving async code
via asyncio.run(), httpx.MockTransport for the Ollama client. No network/DB/gateway.
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx
import pytest

from clay.ai_control.runner import (
    AgentRunner,
    DEFAULT_SYSTEM_PROMPT,
    LiteLLMModelClient,
    ModelResponse,
    ModelUnavailableError,
    OllamaNativeClient,
    ServiceModelResolver,
)
from clay.llm import ChatMessage, ChatCompletionResponse
from clay.settings.ollama import OllamaSettings

class StubResolver:
    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def resolve_model_id(self, role_id: str) -> str:
        return self._mapping.get(role_id, "")

class FakeService:
    def __init__(self, assignments: dict[str, str]) -> None:
        self.assignments = assignments

class RecordingClient:
    def __init__(self, response: ModelResponse) -> None:
        self._response = response
        self.calls: list[dict] = []

    async def chat(self, messages, *, model, think=True, num_predict=None):
        self.calls.append(
            {"messages": messages, "model": model, "think": think, "num_predict": num_predict}
        )
        return self._response

# ---- AgentRunner ----------------------------------------------------------

def test_run_agent_resolves_model_and_returns_content() -> None:
    client = RecordingClient(ModelResponse(content="QUASAR-7741", thinking=None, model="gemma4-e2b"))
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
    assert client.calls[0]["model"] == "gemma4:e2b-it-qat"
    assert client.calls[0]["think"] is True
    assert [m.role for m in result.messages] == ["system", "user"]
    assert result.messages[0].content == "You are the signal agent."
    assert result.messages[1].content == "What is the launch code?"

def test_run_agent_captures_thinking_when_present() -> None:
    client = RecordingClient(ModelResponse(content="42", thinking="let me reason...", model="m"))
    runner = AgentRunner(model_resolver=StubResolver({"r": "m"}), model_client=client)
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

# ---- ServiceModelResolver -------------------------------------------------

def test_service_model_resolver_reads_assignment() -> None:
    resolver = ServiceModelResolver(FakeService({"signal": "gemma4:e2b-it-qat"}))
    assert resolver.resolve_model_id("signal") == "gemma4:e2b-it-qat"

def test_service_model_resolver_missing_role_raises() -> None:
    resolver = ServiceModelResolver(FakeService({}))
    raised = False
    try:
        resolver.resolve_model_id("nope")
    except ValueError:
        raised = True
    assert raised

def test_service_model_resolver_empty_assignment_raises() -> None:
    resolver = ServiceModelResolver(FakeService({"signal": ""}))
    raised = False
    try:
        resolver.resolve_model_id("signal")
    except ValueError:
        raised = True
    assert raised

# ---- OllamaNativeClient: parsing -----------------------------------------

def test_ollama_native_client_parses_thinking_and_content() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gemma4:e2b-it-qat",
                "message": {"role": "assistant", "thinking": "reasoning trace", "content": "QUASAR-7741"},
                "done": True,
            },
        )

    client = OllamaNativeClient(transport=httpx.MockTransport(handler))
    resp = asyncio.run(
        client.chat([ChatMessage(role="user", content="code?")], model="gemma4:e2b-it-qat", think=True, num_predict=256)
    )

    assert resp.content == "QUASAR-7741"
    assert resp.thinking == "reasoning trace"
    assert resp.model == "gemma4:e2b-it-qat"
    assert captured["url"].endswith("/api/chat")
    assert captured["body"]["think"] is True
    assert captured["body"]["stream"] is False
    assert captured["body"]["options"]["num_ctx"] == 65536
    assert captured["body"]["options"]["num_predict"] == 256
    assert captured["body"]["messages"][0] == {"role": "user", "content": "code?"}

def test_ollama_native_client_empty_thinking_is_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "m", "message": {"role": "assistant", "content": "ok", "thinking": ""}})

    client = OllamaNativeClient(transport=httpx.MockTransport(handler))
    resp = asyncio.run(client.chat([ChatMessage(role="user", content="hi")], model="m"))
    assert resp.content == "ok"
    assert resp.thinking is None

# ---- OllamaNativeClient: fail-loud ---------------------------------------

def test_ollama_client_raises_model_unavailable_on_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = OllamaNativeClient(transport=httpx.MockTransport(handler))
    raised = False
    try:
        asyncio.run(client.chat([ChatMessage(role="user", content="x")], model="m"))
    except ModelUnavailableError:
        raised = True
    assert raised

def test_ollama_client_raises_model_unavailable_on_http_500() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = OllamaNativeClient(transport=httpx.MockTransport(handler))
    raised = False
    try:
        asyncio.run(client.chat([ChatMessage(role="user", content="x")], model="m"))
    except ModelUnavailableError:
        raised = True
    assert raised

# ---- OllamaSettings + from_settings --------------------------------------

def test_ollama_settings_defaults() -> None:
    for k in ("CLAY_OLLAMA_BASE_URL", "CLAY_OLLAMA_NUM_CTX", "CLAY_OLLAMA_TIMEOUT_SECONDS"):
        os.environ.pop(k, None)
    s = OllamaSettings()
    assert s.base_url == "http://127.0.0.1:11434"
    assert s.num_ctx == 65536
    assert s.timeout_seconds == 120.0

def test_ollama_settings_env_override() -> None:
    keys = {"CLAY_OLLAMA_BASE_URL": "http://127.0.0.1:9999", "CLAY_OLLAMA_NUM_CTX": "4096"}
    old = {k: os.environ.get(k) for k in keys}
    try:
        os.environ.update(keys)
        s = OllamaSettings()
        assert s.base_url == "http://127.0.0.1:9999"
        assert s.num_ctx == 4096
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

def test_ollama_client_from_settings_uses_settings_values() -> None:
    for k in ("CLAY_OLLAMA_BASE_URL", "CLAY_OLLAMA_NUM_CTX", "CLAY_OLLAMA_TIMEOUT_SECONDS"):
        os.environ.pop(k, None)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"model": "m", "message": {"content": "ok"}})

    client = OllamaNativeClient.from_settings(OllamaSettings(), transport=httpx.MockTransport(handler))
    resp = asyncio.run(client.chat([ChatMessage(role="user", content="hi")], model="m"))
    assert resp.content == "ok"
    assert captured["body"]["options"]["num_ctx"] == 65536


class StubClient:
    async def chat(self, messages, *, model, think=True, num_predict=None):
        return ModelResponse(content="stub")


def test_agent_runner_role_prompts_dispatch_and_fallback() -> None:
    resolver = StubResolver({"test-role": "test-model"})

    role_prompts = {
        "known-role": "Ты известная роль.",
    }
    runner = AgentRunner(
        model_resolver=resolver,
        model_client=StubClient(),
        role_prompts=role_prompts,
    )

    assert runner._system_prompt_for("known-role") == "Ты известная роль."
    assert runner._system_prompt_for("unknown-role") == DEFAULT_SYSTEM_PROMPT
    assert runner._system_prompt_for("") == DEFAULT_SYSTEM_PROMPT


def test_litellm_client_reasoning_content_fallback() -> None:
    """FOOTGUN D: content=null, reasoning_content="thoughts" → content="thoughts".

    Also tests: both empty → ModelUnavailableError.
    """
    from unittest.mock import MagicMock

    from clay.llm import ChatCompletionChoice, ChatMessage as LLMChatMessage
    from clay.llm import LLMAdapter

    adapter = MagicMock(spec=LLMAdapter)

    async def _mock_chat(content: str | None, reasoning: str | None):
        msg = LLMChatMessage(role="assistant", content=content or "", reasoning_content=reasoning)
        choice = ChatCompletionChoice(index=0, message=msg)
        adapter.chat_completion.return_value = ChatCompletionResponse(
            id="test",
            model="gemma-4-31b",
            choices=[choice],
        )
        client = LiteLLMModelClient(adapter=adapter)
        resp = await client.chat([ChatMessage(role="user", content="hi")], model="gemma-4-31b")
        return resp

    # Case 1: content=null, reasoning_content="..." → content="..."
    resp = asyncio.run(_mock_chat(None, "deep thinking result"))
    assert resp.content == "deep thinking result"
    assert resp.thinking is None

    # Case 2: content="ok", reasoning_content="..." → content="ok" (prefer content)
    resp = asyncio.run(_mock_chat("ok", "irrelevant"))
    assert resp.content == "ok"

    # Case 3: both empty → ModelUnavailableError
    with pytest.raises(ModelUnavailableError, match="empty content"):
        asyncio.run(_mock_chat(None, None))
