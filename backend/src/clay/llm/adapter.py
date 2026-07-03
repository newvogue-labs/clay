"""Async httpx adapter for an OpenAI-compatible LLM gateway (LiteLLM).

No external egress happens at import or construction time — only when
``chat_completion`` is awaited. Inject a custom ``transport``
(e.g. ``httpx.MockTransport``) in tests to stay fully offline.
"""

from __future__ import annotations

import logging

import httpx

from clay.llm.models import ChatCompletionRequest, ChatCompletionResponse
from clay.settings.llm import LLMSettings

logger = logging.getLogger(__name__)


def _normalize_response(raw: dict) -> dict:
    """Coerce ``content: null`` → ``""`` in every choice message.

    LiteLLM / upstream providers legitimately return ``content=null`` when the
    model produces only reasoning tokens (no visible text).  Pydantic
    ``ChatMessage.content: str`` rejects ``None`` with a ``ValidationError`` so
    we normalise at the JSON boundary — before ``model_validate`` — rather than
    making ``content`` optional (which would ripple ``None`` through 4+
    downstream readers).

    Returns the mutated dict so the caller can chain:
    ``ChatCompletionResponse.model_validate(_normalize_response(response.json()))``
    """
    for choice in raw.get("choices", []):
        msg = choice.get("message", {})
        if msg.get("content") is None:
            model = raw.get("model", "unknown")
            reasoning = (msg.get("reasoning_content") or "")[:200]
            logger.warning(
                "LiteLLM returned content=null for model %r; "
                "coerced to empty string. reasoning_content=%.200s",
                model,
                reasoning,
            )
            msg["content"] = ""
    return raw


class LLMAdapter:
    def __init__(
        self,
        settings: LLMSettings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings or LLMSettings()
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._settings.master_key:
            headers["Authorization"] = f"Bearer {self._settings.master_key}"
        return headers

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        async with httpx.AsyncClient(
            base_url=self._settings.base_url,
            timeout=self._settings.timeout_seconds,
            transport=self._transport,
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                headers=self._headers(),
                json=request.model_dump(exclude_none=True),
            )
            response.raise_for_status()
            raw = response.json()
            return ChatCompletionResponse.model_validate(_normalize_response(raw))
