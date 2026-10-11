"""Typed provider-neutral contracts for LLM runtime calls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

StructuredT = TypeVar("StructuredT", bound=BaseModel)


class ModelRole(StrEnum):
    """Product-level roles that may have independent model assignments."""

    SUFFICIENCY = "sufficiency"
    GENERATION = "generation"
    EVAL_JUDGE = "eval_judge"
    EMBEDDING = "embedding"


@dataclass(frozen=True, slots=True)
class ModelProvider:
    provider_id: str
    display_name: str

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.display_name.strip():
            raise ValueError("model provider identifiers must not be blank")


@dataclass(frozen=True, slots=True)
class ModelConnection:
    connection_id: str
    provider_id: str
    credential_reference: str
    data_policy: str | None = None

    def __post_init__(self) -> None:
        if not self.connection_id.strip():
            raise ValueError("connection_id must not be blank")
        if not self.provider_id.strip():
            raise ValueError("provider_id must not be blank")
        if not self.credential_reference.strip():
            raise ValueError("credential_reference must not be blank")


@dataclass(frozen=True, slots=True)
class ModelDeployment:
    deployment_id: str
    connection_id: str
    model_identifier: str
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.deployment_id.strip():
            raise ValueError("deployment_id must not be blank")
        if not self.connection_id.strip():
            raise ValueError("connection_id must not be blank")
        if not self.model_identifier.strip():
            raise ValueError("model_identifier must not be blank")


@dataclass(frozen=True, slots=True)
class ModelAssignment:
    role: ModelRole
    primary_deployment_id: str
    fallback_deployment_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.primary_deployment_id.strip():
            raise ValueError("primary_deployment_id must not be blank")
        if any(not item.strip() for item in self.fallback_deployment_ids):
            raise ValueError("fallback deployment IDs must not be blank")
        if len(self.fallback_deployment_ids) != len(set(self.fallback_deployment_ids)):
            raise ValueError("fallback deployment IDs must not contain duplicates")


@dataclass(frozen=True, slots=True)
class LLMInvocationMetadata:
    provider_id: str
    connection_id: str
    deployment_id: str
    model_identifier: str
    prompt_version: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    provider_request_id: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.provider_id,
            self.connection_id,
            self.deployment_id,
            self.model_identifier,
            self.prompt_version,
        ):
            if not value.strip():
                raise ValueError("LLM invocation identifiers must not be blank")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        for value in (self.input_tokens, self.output_tokens, self.total_tokens):
            if value is not None and value < 0:
                raise ValueError("token counts must not be negative")


@dataclass(frozen=True, slots=True)
class TextCompletionRequest:
    system_prompt: str
    user_prompt: str
    prompt_version: str
    temperature: float = 0.0
    max_output_tokens: int = 1024

    def __post_init__(self) -> None:
        if not self.system_prompt.strip() or not self.user_prompt.strip():
            raise ValueError("LLM prompts must not be blank")
        if not self.prompt_version.strip():
            raise ValueError("prompt_version must not be blank")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")


@dataclass(frozen=True, slots=True)
class StructuredCompletionRequest(Generic[StructuredT]):
    system_prompt: str
    user_prompt: str
    prompt_version: str
    response_model: type[StructuredT]
    schema_name: str
    temperature: float = 0.0
    max_output_tokens: int = 1024

    def __post_init__(self) -> None:
        if not self.system_prompt.strip() or not self.user_prompt.strip():
            raise ValueError("LLM prompts must not be blank")
        if not self.prompt_version.strip() or not self.schema_name.strip():
            raise ValueError("prompt/schema identifiers must not be blank")
        if not issubclass(self.response_model, BaseModel):
            raise TypeError("response_model must be a Pydantic BaseModel type")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")


@dataclass(frozen=True, slots=True)
class TextCompletionResult:
    text: str
    metadata: LLMInvocationMetadata

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("text completion must not be blank")


@dataclass(frozen=True, slots=True)
class StructuredCompletionResult(Generic[StructuredT]):
    value: StructuredT
    metadata: LLMInvocationMetadata


class LLMPort(Protocol):
    """Provider-neutral LLM boundary used by application workflows."""

    def complete_text(self, request: TextCompletionRequest) -> TextCompletionResult: ...

    def complete_structured(
        self,
        request: StructuredCompletionRequest[StructuredT],
    ) -> StructuredCompletionResult[StructuredT]: ...
