"""Offline tests for LiteLLMModelClient + RoutingModelClient + transport_for.

DEPLOY-5 / 5b-iii.1. Zero egress: all HTTP calls use httpx.MockTransport.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from clay.ai_control.runner import (
    LiteLLMModelClient,
    ModelResponse,
    ModelUnavailableError,
    RoutingModelClient,
)
from clay.llm import ChatMessage, LLMAdapter
from clay.settings.llm import LLMSettings


class _RecordingClient:
    """ModelClient stub that records calls and returns a canned response."""

    def __init__(self, tag: str, response: ModelResponse | None = None) -> None:
        self._tag = tag
        self._response = response or ModelResponse(content=f"{tag}-ok")
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


def _local_lookup(model_id: str) -> str:
    return "local"


def _cloud_lookup(model_id: str) -> str:
    return "cloud"


def _unknown_lookup(model_id: str) -> str:
    raise ModelUnavailableError(f"model {model_id!r} not found")


def test_routing_local_model_calls_local_client() -> None:
    local = _RecordingClient("local")
    cloud = _RecordingClient("cloud")
    router = RoutingModelClient(
        local_client=local,
        cloud_client=cloud,
        transport_lookup=_local_lookup,
    )
    resp = asyncio.run(
        router.chat([ChatMessage(role="user", content="hi")], model="gemma4:e2b-it-qat")
    )
    assert resp.content == "local-ok"
    assert len(local.calls) == 1
    assert local.calls[0]["model"] == "gemma4:e2b-it-qat"
    assert len(cloud.calls) == 0


def test_routing_cloud_model_calls_cloud_client() -> None:
    local = _RecordingClient("local")
    cloud = _RecordingClient("cloud")
    router = RoutingModelClient(
        local_client=local,
        cloud_client=cloud,
        transport_lookup=_cloud_lookup,
    )
    resp = asyncio.run(
        router.chat([ChatMessage(role="user", content="hi")], model="gemini-2.5-flash")
    )
    assert resp.content == "cloud-ok"
    assert len(cloud.calls) == 1
    assert cloud.calls[0]["model"] == "gemini-2.5-flash"
    assert len(local.calls) == 0


def test_routing_unknown_model_raises_and_touches_no_client() -> None:
    local = _RecordingClient("local")
    cloud = _RecordingClient("cloud")
    router = RoutingModelClient(
        local_client=local,
        cloud_client=cloud,
        transport_lookup=_unknown_lookup,
    )
    raised = False
    try:
        asyncio.run(
            router.chat([ChatMessage(role="user", content="hi")], model="unknown-model")
        )
    except ModelUnavailableError:
        raised = True
    assert raised
    assert len(local.calls) == 0
    assert len(cloud.calls) == 0


# ---- LiteLLMModelClient ---------------------------------------------------


def _openai_chunk(content: str) -> bytes:
    return json.dumps(
        {
            "id": "chatcmpl-abc123",
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    ).encode()


def test_litellm_client_happy_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "gemini-2.5-flash"
        assert body["messages"][0]["role"] == "user"
        return httpx.Response(200, json=json.loads(_openai_chunk("Hello from LiteLLM")))

    adapter = LLMAdapter(
        LLMSettings(base_url="http://test:4000"),
        transport=httpx.MockTransport(handler),
    )
    client = LiteLLMModelClient(adapter=adapter)
    resp = asyncio.run(
        client.chat(
            [ChatMessage(role="user", content="say hi")],
            model="gemini-2.5-flash",
            think=False,
            num_predict=100,
        )
    )
    assert resp.content == "Hello from LiteLLM"
    assert resp.thinking is None


def test_litellm_client_empty_choices_returns_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-empty",
                "model": "m",
                "choices": [],
                "usage": None,
            },
        )

    adapter = LLMAdapter(
        LLMSettings(base_url="http://test:4000"),
        transport=httpx.MockTransport(handler),
    )
    client = LiteLLMModelClient(adapter=adapter)
    with pytest.raises(ModelUnavailableError, match="empty content"):
        asyncio.run(client.chat([ChatMessage(role="user", content="hi")], model="m"))


def test_litellm_client_raises_model_unavailable_on_http_500() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "upstream boom"})

    adapter = LLMAdapter(
        LLMSettings(base_url="http://test:4000"),
        transport=httpx.MockTransport(handler),
    )
    client = LiteLLMModelClient(adapter=adapter)
    raised = False
    try:
        asyncio.run(
            client.chat([ChatMessage(role="user", content="x")], model="m")
        )
    except ModelUnavailableError:
        raised = True
    assert raised


def test_litellm_client_raises_model_unavailable_on_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    adapter = LLMAdapter(
        LLMSettings(base_url="http://test:4000"),
        transport=httpx.MockTransport(handler),
    )
    client = LiteLLMModelClient(adapter=adapter)
    raised = False
    try:
        asyncio.run(
            client.chat([ChatMessage(role="user", content="x")], model="m")
        )
    except ModelUnavailableError:
        raised = True
    assert raised


# ---- FOOTGUN E: gateway error capture (status+body) -----------------------


def test_litellm_client_429_body_in_error_message() -> None:
    """FOOTGUN E: 429 with body → error contains status code + body fragment."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "Rate limit exceeded", "retry_after": 60}})

    adapter = LLMAdapter(
        LLMSettings(base_url="http://test:4000"),
        transport=httpx.MockTransport(handler),
    )
    client = LiteLLMModelClient(adapter=adapter)
    with pytest.raises(ModelUnavailableError) as excinfo:
        asyncio.run(client.chat([ChatMessage(role="user", content="x")], model="m"))
    msg = str(excinfo.value)
    assert "429" in msg
    assert "Rate limit exceeded" in msg


def test_litellm_client_400_empty_body_in_error_message() -> None:
    """FOOTGUN E: 400 empty body → error contains '400' without crash."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="")

    adapter = LLMAdapter(
        LLMSettings(base_url="http://test:4000"),
        transport=httpx.MockTransport(handler),
    )
    client = LiteLLMModelClient(adapter=adapter)
    with pytest.raises(ModelUnavailableError) as excinfo:
        asyncio.run(client.chat([ChatMessage(role="user", content="x")], model="m"))
    msg = str(excinfo.value)
    assert "400" in msg
    # Should not crash on empty body
    assert msg


def test_litellm_client_connect_error_has_type_name() -> None:
    """FOOTGUN E: ConnectError without response → error contains type name, no AttributeError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused to backend")

    adapter = LLMAdapter(
        LLMSettings(base_url="http://test:4000"),
        transport=httpx.MockTransport(handler),
    )
    client = LiteLLMModelClient(adapter=adapter)
    with pytest.raises(ModelUnavailableError) as excinfo:
        asyncio.run(client.chat([ChatMessage(role="user", content="x")], model="m"))
    msg = str(excinfo.value)
    assert "ConnectError" in msg or "connection refused" in msg
    # Ensure no AttributeError is raised trying to access .response
    assert "AttributeError" not in msg


# ---- Registry transport_for -----------------------------------------------


def test_transport_for_all_registry_entries_have_valid_transport() -> None:
    from clay.ai_control.service import AIControlService

    service = AIControlService(
        runtime_manager=None,  # type: ignore[arg-type]
        preflight_service=None,  # type: ignore[arg-type]
        config_loader=None,  # type: ignore[arg-type]
        audit_writer=None,  # type: ignore[arg-type]
        event_bus=None,  # type: ignore[arg-type]
    )
    for model_id, entry in service.models.items():
        assert entry.transport in (
            "local",
            "cloud",
        ), f"{model_id}: unexpected transport={entry.transport!r}"
        resolved = service.transport_for(model_id)
        assert resolved == entry.transport


def test_transport_for_unknown_model_raises() -> None:
    from clay.ai_control.service import AIControlService

    service = AIControlService(
        runtime_manager=None,  # type: ignore[arg-type]
        preflight_service=None,  # type: ignore[arg-type]
        config_loader=None,  # type: ignore[arg-type]
        audit_writer=None,  # type: ignore[arg-type]
        event_bus=None,  # type: ignore[arg-type]
    )
    raised = False
    try:
        service.transport_for("model-that-does-not-exist")
    except ModelUnavailableError:
        raised = True
    assert raised


def test_transport_for_minimax_m3_is_cloud() -> None:
    from clay.ai_control.service import AIControlService

    service = AIControlService(
        runtime_manager=None,  # type: ignore[arg-type]
        preflight_service=None,  # type: ignore[arg-type]
        config_loader=None,  # type: ignore[arg-type]
        audit_writer=None,  # type: ignore[arg-type]
        event_bus=None,  # type: ignore[arg-type]
    )
    assert "minimax-m3" in service.models
    assert service.models["minimax-m3"].transport == "cloud"
    assert service.transport_for("minimax-m3") == "cloud"


def test_transport_for_gemini_3_1_flash_lite_is_cloud() -> None:
    from clay.ai_control.service import AIControlService

    service = AIControlService(
        runtime_manager=None,  # type: ignore[arg-type]
        preflight_service=None,  # type: ignore[arg-type]
        config_loader=None,  # type: ignore[arg-type]
        audit_writer=None,  # type: ignore[arg-type]
        event_bus=None,  # type: ignore[arg-type]
    )
    assert "gemini-3.1-flash-lite" in service.models
    assert service.models["gemini-3.1-flash-lite"].transport == "cloud"
    assert service.transport_for("gemini-3.1-flash-lite") == "cloud"
