"""Ollama runtime settings (CLAY_OLLAMA_*).

The local model is served by Ollama on loopback; AgentRunner's
OllamaNativeClient uses these to reach the native /api/chat endpoint.
Mirrors the LLMSettings (CLAY_LLM_*) convention.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class OllamaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLAY_OLLAMA_", extra="ignore")

    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 120.0
    num_ctx: int = 65536
