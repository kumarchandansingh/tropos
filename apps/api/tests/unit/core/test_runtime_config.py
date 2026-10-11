from __future__ import annotations

import pytest

from tropos.core.runtime_config import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    LLMRuntimeSettings,
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
