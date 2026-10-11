"""Typed runtime configuration for external LLM access.

Secrets are read from the process environment and are never given defaults,
serialized, or included in repr output. Provider adapters consume this contract;
domain/evaluation code must not read environment variables directly.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


DEFAULT_LLM_PROVIDER = "groq"
DEFAULT_LLM_MODEL = "openai/gpt-oss-120b"


@dataclass(frozen=True, slots=True)
class LLMRuntimeSettings:
    """Minimal bootstrap configuration for the first real Tropos LLM provider."""

    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    api_key: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("LLM provider must not be blank")
        if not self.model.strip():
            raise ValueError("LLM model must not be blank")
        if self.api_key is not None and not self.api_key.strip():
            raise ValueError("LLM API key must be omitted or non-blank")

    @property
    def configured(self) -> bool:
        """Return whether a usable provider credential is available."""

        return self.api_key is not None

    def require_api_key(self) -> str:
        """Return the secret for adapter construction or fail closed."""

        if self.api_key is None:
            raise RuntimeError(
                "Tropos LLM credential is not configured. "
                "Set TROPOS_GROQ_API_KEY in the runtime environment."
            )
        return self.api_key


def load_llm_runtime_settings(
    environ: Mapping[str, str] | None = None,
) -> LLMRuntimeSettings:
    """Load the current LLM bootstrap settings from environment variables."""

    values = os.environ if environ is None else environ
    provider = values.get("TROPOS_LLM_PROVIDER", DEFAULT_LLM_PROVIDER).strip()
    model = values.get("TROPOS_LLM_MODEL", DEFAULT_LLM_MODEL).strip()
    raw_key = values.get("TROPOS_GROQ_API_KEY")
    api_key = raw_key.strip() if raw_key is not None else None

    return LLMRuntimeSettings(
        provider=provider,
        model=model,
        api_key=api_key,
    )
