"""Groq adapter implementing the provider-neutral Tropos LLM port."""

from __future__ import annotations

import json
import socket
from collections.abc import Mapping
from time import monotonic
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel

from tropos.core.application.ports.llm import (
    LLMInvocationMetadata,
    ModelConnection,
    ModelDeployment,
    StructuredCompletionRequest,
    StructuredCompletionResult,
    TextCompletionRequest,
    TextCompletionResult,
)
from tropos.core.runtime_config import LLMRuntimeSettings

_GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
_TROPOS_USER_AGENT = "tropos/0.1"


class LLMProviderError(RuntimeError):
    """Provider call failed before a valid Tropos result could be produced."""


class LLMTimeoutError(LLMProviderError):
    """Provider call exceeded the configured timeout."""


class LLMResponseError(LLMProviderError):
    """Provider returned an invalid or unexpected response shape."""


class JsonTransport(Protocol):
    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]: ...


class UrllibJsonTransport:
    """Small standard-library JSON transport; provider details stay in this adapter."""

    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        request = Request(
            url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = self._http_error_detail(exc)
            message = f"Groq returned HTTP {exc.code}"
            if detail is not None:
                message = f"{message}: {detail}"
            raise LLMProviderError(message) from exc
        except TimeoutError as exc:
            raise LLMTimeoutError("Groq request timed out") from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise LLMTimeoutError("Groq request timed out") from exc
            raise LLMProviderError("Groq request failed") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMResponseError("Groq returned non-JSON output") from exc
        if not isinstance(parsed, dict):
            raise LLMResponseError("Groq returned an unexpected JSON shape")
        return cast(dict[str, object], parsed)

    @staticmethod
    def _http_error_detail(exc: HTTPError) -> str | None:
        """Extract a bounded provider message without exposing request credentials."""

        try:
            raw = exc.read(16_384)
        except OSError:
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError, UnicodeDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        if not isinstance(error, dict):
            return None
        message = error.get("message")
        if not isinstance(message, str):
            return None
        normalized = " ".join(message.split())
        return normalized[:500] or None


class GroqLLMAdapter:
    """Groq chat-completions adapter with strict structured-output support."""

    def __init__(
        self,
        *,
        api_key: str,
        connection: ModelConnection,
        deployment: ModelDeployment,
        timeout_seconds: float = 30.0,
        transport: JsonTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Groq API key must not be blank")
        if connection.provider_id != "groq":
            raise ValueError("Groq adapter requires a groq connection")
        if deployment.connection_id != connection.connection_id:
            raise ValueError("deployment must belong to the configured connection")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._api_key = api_key
        self._connection = connection
        self._deployment = deployment
        self._timeout_seconds = timeout_seconds
        self._transport = transport or UrllibJsonTransport()

    def __repr__(self) -> str:
        return (
            "GroqLLMAdapter("
            f"connection_id={self._connection.connection_id!r}, "
            f"deployment_id={self._deployment.deployment_id!r})"
        )

    @property
    def connection(self) -> ModelConnection:
        return self._connection

    @property
    def deployment(self) -> ModelDeployment:
        return self._deployment

    def complete_text(self, request: TextCompletionRequest) -> TextCompletionResult:
        payload = self._base_payload(request)
        response, latency_ms = self._invoke(payload)
        text = self._content(response)
        return TextCompletionResult(
            text=text,
            metadata=self._metadata(
                response=response,
                prompt_version=request.prompt_version,
                latency_ms=latency_ms,
            ),
        )

    def complete_structured[StructuredT: BaseModel](
        self,
        request: StructuredCompletionRequest[StructuredT],
    ) -> StructuredCompletionResult[StructuredT]:
        payload = self._base_payload(request)
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": request.schema_name,
                "strict": True,
                "schema": request.response_model.model_json_schema(),
            },
        }
        response, latency_ms = self._invoke(payload)
        content = self._content(response)
        try:
            value = request.response_model.model_validate_json(content)
        except ValueError as exc:
            raise LLMResponseError("Groq structured output failed schema validation") from exc
        return StructuredCompletionResult(
            value=value,
            metadata=self._metadata(
                response=response,
                prompt_version=request.prompt_version,
                latency_ms=latency_ms,
            ),
        )

    def _base_payload[StructuredT: BaseModel](
        self,
        request: TextCompletionRequest | StructuredCompletionRequest[StructuredT],
    ) -> dict[str, object]:
        return {
            "model": self._deployment.model_identifier,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "max_completion_tokens": request.max_output_tokens,
        }

    def _invoke(self, payload: Mapping[str, object]) -> tuple[dict[str, object], float]:
        started = monotonic()
        response = self._transport.post(
            url=_GROQ_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": _TROPOS_USER_AGENT,
            },
            payload=payload,
            timeout_seconds=self._timeout_seconds,
        )
        return response, (monotonic() - started) * 1000.0

    @staticmethod
    def _content(response: Mapping[str, object]) -> str:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMResponseError("Groq response contains no choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise LLMResponseError("Groq choice has an unexpected shape")
        message = first.get("message")
        if not isinstance(message, dict):
            raise LLMResponseError("Groq choice contains no message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("Groq response content is blank")
        return content

    def _metadata(
        self,
        *,
        response: Mapping[str, object],
        prompt_version: str,
        latency_ms: float,
    ) -> LLMInvocationMetadata:
        usage = response.get("usage")
        usage_map = usage if isinstance(usage, dict) else {}

        choices = response.get("choices")
        finish_reason: str | None = None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            raw_finish = choices[0].get("finish_reason")
            if isinstance(raw_finish, str):
                finish_reason = raw_finish

        request_id = response.get("id")
        return LLMInvocationMetadata(
            provider_id=self._connection.provider_id,
            connection_id=self._connection.connection_id,
            deployment_id=self._deployment.deployment_id,
            model_identifier=self._deployment.model_identifier,
            prompt_version=prompt_version,
            latency_ms=latency_ms,
            input_tokens=self._optional_int(usage_map.get("prompt_tokens")),
            output_tokens=self._optional_int(usage_map.get("completion_tokens")),
            total_tokens=self._optional_int(usage_map.get("total_tokens")),
            finish_reason=finish_reason,
            provider_request_id=request_id if isinstance(request_id, str) else None,
        )

    @staticmethod
    def _optional_int(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None


def build_default_groq_llm(settings: LLMRuntimeSettings) -> GroqLLMAdapter:
    """Build the first environment-backed Groq connection/deployment."""

    if settings.provider != "groq":
        raise ValueError("default runtime factory currently supports only provider=groq")

    connection = ModelConnection(
        connection_id="groq-default",
        provider_id="groq",
        credential_reference="env:TROPOS_GROQ_API_KEY",
        data_policy="configured-outside-source-control",
    )
    deployment = ModelDeployment(
        deployment_id=f"groq:{settings.model}",
        connection_id=connection.connection_id,
        model_identifier=settings.model,
        capabilities=("text", "structured-output"),
    )
    return GroqLLMAdapter(
        api_key=settings.require_api_key(),
        connection=connection,
        deployment=deployment,
    )
