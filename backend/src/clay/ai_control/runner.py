"""AgentRunner + transport for a single AI-control agent turn.

DEPLOY-5:
- 5b-ii.1: AgentRunner, ModelClient/ModelResolver protocols, OllamaNativeClient,
  ModelResponse/AgentRunResult.
- 5b-ii.2a: ServiceModelResolver (reads ai_control_service.assignments),
  OllamaNativeClient.from_settings, fail-loud ModelUnavailableError.

Transport decision:
- LOCAL model (Gemma via Ollama) -> NATIVE Ollama API (/api/chat), NOT the
  LiteLLM gateway: the OpenAI-compat /v1 endpoint returns empty `content` for
  Gemma's thinking template (Ollama #15288). Native API separates `thinking`
  and `content`.
- EXTERNAL providers (Gemini, 5b-iii) -> LiteLLM gateway via the committed
  LLMAdapter; both satisfy the ModelClient protocol.
- Fail-loud (ADR-009): a backend that cannot be reached raises
  ModelUnavailableError; never silently fall back.
- Persistence + scheduler wiring -> 5b-ii.2b.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx

from clay.llm import ChatCompletionRequest, ChatMessage, LLMAdapter
from clay.llm import ChatCompletionResponse as _ChatCompletionResponse

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_NUM_CTX = 65536
DEFAULT_SYSTEM_PROMPT = (
    "You are a Clay assistant agent. Be precise and concise. "
    "Base your answer only on the provided context."
)

class ModelUnavailableError(RuntimeError):
    """Raised when a model backend cannot be reached or returns an error.

    Fail-loud (ADR-009): callers must surface this; never silently fall back
    to another provider or to stale/empty output.
    """


def _format_gateway_error(exc: httpx.HTTPError, *, model: str, base_url: str) -> str:
    """Format an ``httpx.HTTPError`` into a descriptive error message.

    For HTTPStatusError (4xx/5xx) includes status code + truncated body.
    For transport errors (ConnectError, Timeout) includes exception type and message.
    Body is capped at 500 characters.
    """
    status = getattr(exc, "response", None)
    if status is not None:
        body = (status.text or "")[:500]
        return (
            f"gateway HTTP {status.status_code} for model {model!r} "
            f"at {base_url}: {body}"
        )
    return (
        f"gateway call failed for model {model!r} at {base_url}: "
        f"[{type(exc).__name__}] {exc}"
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
    """Transport-agnostic chat interface."""

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
    """Resolves a role id to its assigned model id."""

    def resolve_model_id(self, role_id: str) -> str: ...

@runtime_checkable
class _AssignmentsProvider(Protocol):
    assignments: dict[str, str]

@runtime_checkable
class _OllamaSettingsLike(Protocol):
    base_url: str
    timeout_seconds: float
    num_ctx: int

class ServiceModelResolver:
    """ModelResolver backed by ai_control_service.assignments.

    assignments is dict[str, str] (role_id -> model_id). Governance/validation
    lives in the service (it populates assignments via _validate_role_and_model);
    this resolver does NOT duplicate it — it only reads.
    """

    def __init__(self, service: _AssignmentsProvider) -> None:
        self._service = service

    def resolve_model_id(self, role_id: str) -> str:
        try:
            model_id = self._service.assignments[role_id]
        except KeyError:
            raise ValueError(f"no model assigned for role_id={role_id!r}") from None
        if not model_id:
            raise ValueError(f"empty model assignment for role_id={role_id!r}")
        return model_id

class OllamaNativeClient:
    """ModelClient backed by the native Ollama /api/chat endpoint.

    Native API (not /v1) so `thinking` and `content` come back separately.
    Inject `transport` for offline tests (httpx.MockTransport). Any transport
    or HTTP-status failure is raised as ModelUnavailableError (fail-loud).
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

    @classmethod
    def from_settings(
        cls,
        settings: _OllamaSettingsLike,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "OllamaNativeClient":
        return cls(
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
            num_ctx=settings.num_ctx,
            transport=transport,
        )

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
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                resp = await client.post("/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise ModelUnavailableError(
                _format_gateway_error(exc, model=model, base_url=self._base_url)
            ) from exc
        message = data.get("message", {}) or {}
        return ModelResponse(
            content=message.get("content", "") or "",
            thinking=(message.get("thinking") or None),
            model=data.get("model", model),
            raw=data,
        )

class LiteLLMModelClient:
    """ModelClient backed by the LiteLLM gateway via LLMAdapter.

    Wraps ``LLMAdapter.chat_completion()`` (OpenAI-compatible /v1 endpoint).
    ``thinking`` is always ``None`` — cloud models do not expose separate
    thinking traces through this path. Inject ``adapter`` with a custom
    ``httpx.AsyncBaseTransport`` for offline tests.
    """

    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        think: bool = True,
        num_predict: int | None = None,
    ) -> ModelResponse:
        request = ChatCompletionRequest(
            model=model,
            messages=messages,
            max_tokens=num_predict,
        )
        try:
            response: _ChatCompletionResponse = await self._adapter.chat_completion(request)
        except httpx.HTTPError as exc:
            raise ModelUnavailableError(
                _format_gateway_error(
                    exc, model=model, base_url=self._adapter._settings.base_url
                )
            ) from exc
        choice = response.choices[0] if response.choices else None
        content = (choice.message.content or None) if choice else None
        reasoning = (choice.message.reasoning_content or None) if choice else None
        content = content or reasoning
        if not content:
            raise ModelUnavailableError(
                f"LiteLLM gateway returned empty content for model {model!r}"
            )
        return ModelResponse(content=content, thinking=None)


class RoutingModelClient:
    """Composite ModelClient that dispatches per-call by transport.

    Holds both a local and a cloud ``ModelClient``. On each ``chat()`` call
    it looks up the transport for ``model_id`` via the injected
    ``transport_lookup`` and delegates to the appropriate client.

    ``transport_lookup(model_id) -> "local" | "cloud"`` — any other return
    value or ``ModelUnavailableError`` is propagated fail-loud.

    Lifespan wiring stays trivial: build two clients, wrap in this, pass to
    ``AgentRunner``.
    """

    def __init__(
        self,
        *,
        local_client: ModelClient,
        cloud_client: ModelClient,
        transport_lookup: Callable[[str], str],
    ) -> None:
        self._local = local_client
        self._cloud = cloud_client
        self._lookup = transport_lookup

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        think: bool = True,
        num_predict: int | None = None,
    ) -> ModelResponse:
        transport = self._lookup(model)
        if transport == "local":
            return await self._local.chat(
                messages, model=model, think=think, num_predict=num_predict
            )
        if transport == "cloud":
            return await self._cloud.chat(
                messages, model=model, think=think, num_predict=num_predict
            )
        raise ModelUnavailableError(
            f"unknown transport {transport!r} for model {model!r}; "
            f"expected 'local' or 'cloud'"
        )


class AgentRunner:
    """Runs one agent turn for a given role.

    1. Resolve the role's assigned model id (injected ModelResolver).
    2. Assemble messages: role system prompt + caller context.
    3. Call the injected ModelClient (local => native Ollama).
    4. Return a normalized AgentRunResult.

    Propagates ModelUnavailableError fail-loud. Persistence -> 5b-ii.2b.
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
