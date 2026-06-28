"""LLM gateway settings (CLAY_LLM_*).

Mirrors the ``AuditSettings`` / ``IngestionSettings`` pattern
(pydantic-settings, ``env_prefix`` with ``extra="ignore"``).

Read at the composition boundary (``LLMAdapter`` construction) — the
settings module should not be imported deep in the call graph.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Configuration for the OpenAI-compatible LLM gateway (LiteLLM).

    * ``base_url`` — base URL of the gateway (default local LiteLLM
      ``http://127.0.0.1:4000``). Env: ``CLAY_LLM_BASE_URL``.
    * ``master_key`` — optional bearer token; omitted by default
      (local/dev gateway typically doesn't require auth).
      Env: ``CLAY_LLM_MASTER_KEY``.
    * ``timeout_seconds`` — per-request timeout in seconds.
      Env: ``CLAY_LLM_TIMEOUT_SECONDS``.
    """

    model_config = SettingsConfigDict(
        env_prefix="CLAY_LLM_",
        extra="ignore",
    )

    base_url: str = "http://127.0.0.1:4000"
    master_key: str | None = None
    timeout_seconds: float = 30.0
