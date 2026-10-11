from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

import pytest
from pydantic import BaseModel

from tropos.core.adapters.llm.fake import FakeLLM
from tropos.core.adapters.llm.groq import (
    GroqLLMAdapter,
    JsonTransport,
    LLMResponseError,
    build_default_groq_llm,
)
from tropos.core.application.ports.llm import (
    ModelConnection,
    ModelDeployment,
    StructuredCompletionRequest,
    TextCompletionRequest,
)
from tropos.core.runtime_config import LLMRuntimeSettings


class HealthResult(BaseModel):
    status: Literal["ok"]


class RecordingTransport(JsonTransport):
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.url: str | None = None
        self.headers: Mapping[str, str] | None = None
        self.payload: Mapping[str, object] | None = None
        self.timeout_seconds: float | None = None

    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        self.url = url
        self.headers = headers
        self.payload = payload
        self.timeout_seconds = timeout_seconds
        return self.response


def _adapter(transport: JsonTransport, secret: str = "gsk_secret") -> GroqLLMAdapter:
    connection = ModelConnection(
        connection_id="groq-test",
        provider_id="groq",
        credential_reference="env:TROPOS_GROQ_API_KEY",
    )
    deployment = ModelDeployment(
        deployment_id="groq:test-model",
        connection_id=connection.connection_id,
        model_identifier="test-model",
        capabilities=("text", "structured-output"),
    )
    return GroqLLMAdapter(
        api_key=secret,
        connection=connection,
        deployment=deployment,
        transport=transport,
    )


def test_groq_structured_completion_sends_schema_and_captures_usage() -> None:
    transport = RecordingTransport(
        {
            "id": "req-123",
            "choices": [
                {
                    "message": {"content": '{"status":"ok"}'},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 3,
                "total_tokens": 14,
            },
        }
    )
    adapter = _adapter(transport)

    result = adapter.complete_structured(
        StructuredCompletionRequest(
            system_prompt="Judge the input.",
            user_prompt="Health check.",
            prompt_version="health-v1",
            response_model=HealthResult,
            schema_name="health_result",
        )
    )

    assert result.value.status == "ok"
    assert result.metadata.input_tokens == 11
    assert result.metadata.output_tokens == 3
    assert result.metadata.provider_request_id == "req-123"
    assert transport.payload is not None
    response_format = transport.payload["response_format"]
    assert isinstance(response_format, dict)
    assert response_format["type"] == "json_schema"


def test_groq_secret_is_not_exposed_in_repr() -> None:
    secret = "gsk_super_secret"
    adapter = _adapter(
        RecordingTransport({"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]}),
        secret=secret,
    )

    assert secret not in repr(adapter)


def test_groq_rejects_malformed_structured_output() -> None:
    adapter = _adapter(
        RecordingTransport(
            {"choices": [{"message": {"content": '{"status":"bad"}'}, "finish_reason": "stop"}]}
        )
    )

    with pytest.raises(LLMResponseError, match="schema validation"):
        adapter.complete_structured(
            StructuredCompletionRequest(
                system_prompt="Judge.",
                user_prompt="Input.",
                prompt_version="health-v1",
                response_model=HealthResult,
                schema_name="health_result",
            )
        )


def test_fake_llm_supports_text_and_structured_contracts() -> None:
    fake = FakeLLM(
        text_outputs=("OK",),
        structured_outputs=(HealthResult(status="ok"),),
    )

    text_result = fake.complete_text(
        TextCompletionRequest(
            system_prompt="System",
            user_prompt="User",
            prompt_version="text-v1",
        )
    )
    structured_result = fake.complete_structured(
        StructuredCompletionRequest(
            system_prompt="System",
            user_prompt="User",
            prompt_version="structured-v1",
            response_model=HealthResult,
            schema_name="health_result",
        )
    )

    assert text_result.text == "OK"
    assert structured_result.value.status == "ok"
    assert structured_result.metadata.provider_id == "fake"


def test_default_factory_uses_runtime_settings_without_exposing_secret() -> None:
    secret = "gsk_runtime_secret"
    adapter = build_default_groq_llm(
        LLMRuntimeSettings(
            provider="groq",
            model="openai/gpt-oss-120b",
            api_key=secret,
        )
    )

    assert adapter.deployment.model_identifier == "openai/gpt-oss-120b"
    assert adapter.connection.credential_reference == "env:TROPOS_GROQ_API_KEY"
    assert secret not in repr(adapter)
