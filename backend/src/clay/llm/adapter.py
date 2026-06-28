"""Async httpx adapter for an OpenAI-compatible LLM gateway (LiteLLM).

No external egress happens at import or construction time — only when
``chat_completion`` is awaited. Inject a custom ``transport``
(e.g. ``httpx.MockTransport``) in tests to stay fully offline.
"""

from __future__ import annotations

import httpx

from clay.llm.models import ChatCompletionRequest, ChatCompletionResponse
from clay.settings.llm import LLMSettings


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
            return ChatCompletionResponse.model_validate(response.json())
