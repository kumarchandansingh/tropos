"""Deterministic LLM adapter for tests and local workflow composition."""

from __future__ import annotations

from pydantic import BaseModel

from tropos.core.application.ports.llm import (
    LLMInvocationMetadata,
    StructuredCompletionRequest,
    StructuredCompletionResult,
    TextCompletionRequest,
    TextCompletionResult,
)


class FakeLLM:
    def __init__(
        self,
        *,
        text_outputs: tuple[str, ...] = (),
        structured_outputs: tuple[BaseModel, ...] = (),
    ) -> None:
        self._text_outputs = list(text_outputs)
        self._structured_outputs = list(structured_outputs)

    def _metadata(self, prompt_version: str) -> LLMInvocationMetadata:
        return LLMInvocationMetadata(
            provider_id="fake",
            connection_id="fake",
            deployment_id="fake",
            model_identifier="fake-model",
            prompt_version=prompt_version,
            latency_ms=0.0,
        )

    def complete_text(self, request: TextCompletionRequest) -> TextCompletionResult:
        if not self._text_outputs:
            raise RuntimeError("FakeLLM has no text output configured")
        return TextCompletionResult(
            text=self._text_outputs.pop(0),
            metadata=self._metadata(request.prompt_version),
        )

    def complete_structured[StructuredT: BaseModel](
        self,
        request: StructuredCompletionRequest[StructuredT],
    ) -> StructuredCompletionResult[StructuredT]:
        if not self._structured_outputs:
            raise RuntimeError("FakeLLM has no structured output configured")
        candidate = self._structured_outputs.pop(0)
        value = request.response_model.model_validate(candidate.model_dump())
        return StructuredCompletionResult(
            value=value,
            metadata=self._metadata(request.prompt_version),
        )
