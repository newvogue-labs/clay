"""Clay LLM layer: adapter + models for the OpenAI-compatible gateway."""

from clay.llm.adapter import LLMAdapter
from clay.llm.models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatMessage,
)

__all__ = [
    "LLMAdapter",
    "ChatMessage",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatCompletionChoice",
    "ChatCompletionUsage",
]
