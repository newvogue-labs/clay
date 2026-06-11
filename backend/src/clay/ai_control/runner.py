"""AgentRunner: orchestrates a single AI-control agent turn.

DEPLOY-5 / 5b-ii.1.

Transport decision:
- LOCAL model (Gemma via Ollama) is called through the NATIVE Ollama API
  (/api/chat), NOT the LiteLLM gateway: the OpenAI-compat /v1 endpoint returns
  an empty `content` for Gemma's thinking template (Ollama issue #15288).
  Native /api/chat cleanly separates `thinking` and `content`.
- EXTERNAL providers (Gemini, 5b-iii) go through the LiteLLM gateway via the
  committed LLMAdapter; both satisfy the ModelClient protocol.
- Persistence and live wiring to ai_control_service.assignments[role_id] are
  DEFERRED to 5b-ii.2. This module stays pure/offline-testable: model
  resolution is injected (ModelResolver), governance stays in the service and
  is NOT duplicated here; the HTTP transport is injected for tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx

from clay.llm import ChatMessage

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_NUM_CTX = 65536
DEFAULT_SYSTEM_PROMPT = (
    "You are a Clay assistant agent. Be precise and concise. "
    "Base your answer only on the provided context."
)

@dataclass(slots=True)
class ModelResponse:
    """Normalized result of a single model call."""

    content: str
    thinking: str | None = None
    model: str | None = None
    raw: dict | None = None

@dataclass(slots=True)
class AgentRunResult:
    """Outcome of one AgentRunner.run_agent turn."""

    role_id: str
    model_id: str
    content: str
    thinking: str | None
    messages: list[ChatMessage]

@runtime_checkable
class ModelClient(Protocol):
    """Transport-agnostic chat interface.

    Implementations: OllamaNativeClient (local, native /api/chat) and a
    gateway-backed adapter for external providers (added in 5b-iii).
    """

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        think: bool = True,
        num_predict: int | None = None,
    ) -> ModelResponse: ...

@runtime_checkable
class ModelResolver(Protocol):
    """Resolves a role id to the model id assigned by ai_control governance.

    Production impl (5b-ii.2) reads ai_control_service.assignments[role_id].
    Governance/validation stays in the service and is NOT duplicated here.
    """

    def resolve_model_id(self, role_id: str) -> str: ...

class OllamaNativeClient:
    """ModelClient backed by the native Ollama /api/chat endpoint.

    Native API (not /v1) so `thinking` and `content` come back as separate
    fields. Inject `transport` for offline tests (httpx.MockTransport),
    mirroring tests/llm/test_adapter.py.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        num_ctx: int = DEFAULT_NUM_CTX,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._num_ctx = num_ctx
        self._transport = transport

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        think: bool = True,
        num_predict: int | None = None,
    ) -> ModelResponse:
        options: dict[str, int] = {"num_ctx": self._num_ctx}
        if num_predict is not None:
            options["num_predict"] = num_predict
        payload = {
            "model": model,
            "messages": [
                {"role": m.role, "content": m.content} for m in messages
            ],
            "stream": False,
            "think": think,
            "options": options,
        }
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
        ) as client:
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        message = data.get("message", {}) or {}
        return ModelResponse(
            content=message.get("content", "") or "",
            thinking=(message.get("thinking") or None),
            model=data.get("model", model),
            raw=data,
        )

class AgentRunner:
    """Runs one agent turn for a given role.

    Steps (5b-ii.1):
      1. Resolve the role's assigned model id (injected ModelResolver).
      2. Assemble messages: role system prompt + caller context.
      3. Call the injected ModelClient (local => native Ollama).
      4. Return a normalized AgentRunResult (content + thinking + trace).

    Persistence and live service wiring are DEFERRED to 5b-ii.2.
    """

    def __init__(
        self,
        *,
        model_resolver: ModelResolver,
        model_client: ModelClient,
        role_prompts: dict[str, str] | None = None,
        default_system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        think: bool = True,
        num_predict: int | None = None,
    ) -> None:
        self._resolver = model_resolver
        self._client = model_client
        self._role_prompts = role_prompts or {}
        self._default_system_prompt = default_system_prompt
        self._think = think
        self._num_predict = num_predict

    def _system_prompt_for(self, role_id: str) -> str:
        return self._role_prompts.get(role_id, self._default_system_prompt)

    def _build_messages(self, role_id: str, context: str) -> list[ChatMessage]:
        return [
            ChatMessage(role="system", content=self._system_prompt_for(role_id)),
            ChatMessage(role="user", content=context),
        ]

    async def run_agent(self, role_id: str, context: str) -> AgentRunResult:
        if not role_id:
            raise ValueError("role_id must be a non-empty string")
        model_id = self._resolver.resolve_model_id(role_id)
        if not model_id:
            raise ValueError(f"no model assigned for role_id={role_id!r}")
        messages = self._build_messages(role_id, context)
        response = await self._client.chat(
            messages,
            model=model_id,
            think=self._think,
            num_predict=self._num_predict,
        )
        return AgentRunResult(
            role_id=role_id,
            model_id=model_id,
            content=response.content,
            thinking=response.thinking,
            messages=messages,
        )
