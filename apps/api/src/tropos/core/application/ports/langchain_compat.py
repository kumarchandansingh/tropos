"""Minimal typed boundary for legacy LangChain structured-output adapters."""

from typing import Protocol

from pydantic import BaseModel


class StructuredInvoker(Protocol):
    def invoke(self, messages: object) -> object: ...


class SupportsStructuredOutput(Protocol):
    def with_structured_output(self, schema: type[BaseModel]) -> StructuredInvoker: ...
