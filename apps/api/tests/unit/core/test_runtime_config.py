from __future__ import annotations

import pytest

from tropos.core.runtime_config import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    EmbeddingRuntimeSettings,
    LLMRuntimeSettings,
    RetrievalStrategy,
    load_embedding_runtime_settings,
    load_llm_runtime_settings,
)


def test_runtime_settings_default_to_groq_gpt_oss_without_secret() -> None:
    settings = load_llm_runtime_settings({})

    assert settings.provider == DEFAULT_LLM_PROVIDER
    assert settings.model == DEFAULT_LLM_MODEL
    assert settings.configured is False


def test_runtime_settings_load_secret_without_exposing_it_in_repr() -> None:
    secret = "gsk_test_secret"
    settings = load_llm_runtime_settings({"TROPOS_GROQ_API_KEY": secret})

    assert settings.configured is True
    assert settings.require_api_key() == secret
    assert secret not in repr(settings)


def test_runtime_settings_allow_provider_and_model_override() -> None:
    settings = load_llm_runtime_settings(
        {
            "TROPOS_LLM_PROVIDER": "custom-provider",
            "TROPOS_LLM_MODEL": "custom-model",
            "TROPOS_GROQ_API_KEY": "secret",
        }
    )

    assert settings.provider == "custom-provider"
    assert settings.model == "custom-model"


def test_runtime_settings_fail_closed_when_secret_is_missing() -> None:
    settings = LLMRuntimeSettings()

    with pytest.raises(RuntimeError, match="TROPOS_GROQ_API_KEY"):
        settings.require_api_key()


def test_blank_secret_is_rejected() -> None:
    with pytest.raises(ValueError, match="API key"):
        load_llm_runtime_settings({"TROPOS_GROQ_API_KEY": "   "})



def test_embedding_runtime_defaults_are_unconfigured_and_secret_safe() -> None:
    settings = load_embedding_runtime_settings({})

    assert settings.provider == "openai"
    assert settings.model == "text-embedding-3-small"
    assert settings.dimensions == 1536
    assert settings.configured is False
    assert tuple(strategy.value for strategy in RetrievalStrategy) == (
        "bm25",
        "dense_exact",
        "hybrid_rrf",
    )


def test_embedding_runtime_loads_secret_without_repr_exposure() -> None:
    secret = "sk-test-embedding"
    settings = load_embedding_runtime_settings(
        {
            "TROPOS_EMBEDDING_PROVIDER": "openai",
            "TROPOS_EMBEDDING_MODEL": "text-embedding-3-small",
            "TROPOS_EMBEDDING_DIMENSIONS": "256",
            "TROPOS_OPENAI_API_KEY": secret,
        }
    )

    assert settings.configured is True
    assert settings.dimensions == 256
    assert settings.require_api_key() == secret
    assert secret not in repr(settings)


def test_embedding_runtime_fails_closed_without_secret() -> None:
    with pytest.raises(RuntimeError, match="TROPOS_OPENAI_API_KEY"):
        EmbeddingRuntimeSettings().require_api_key()


def test_embedding_dimensions_must_be_integer() -> None:
    with pytest.raises(ValueError, match="must be an integer"):
        load_embedding_runtime_settings({"TROPOS_EMBEDDING_DIMENSIONS": "many"})
