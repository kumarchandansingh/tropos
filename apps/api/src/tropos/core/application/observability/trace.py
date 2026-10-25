"""Small vendor-neutral trace model and local JSONL sink."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import ContextManager, Protocol

TraceScalar = str | int | float | bool | None
TraceValue = TraceScalar | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TraceSpan:
    name: str
    status: str
    attributes: dict[str, TraceValue]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("trace span name must not be blank")
        if not self.status.strip():
            raise ValueError("trace span status must not be blank")


@dataclass(frozen=True, slots=True)
class RuntimeTrace:
    trace_id: str
    request_id: str
    outcome: str
    spans: tuple[TraceSpan, ...]

    def __post_init__(self) -> None:
        if not self.trace_id.strip() or not self.request_id.strip():
            raise ValueError("trace/request IDs must not be blank")
        if not self.outcome.strip():
            raise ValueError("trace outcome must not be blank")
        if not self.spans:
            raise ValueError("runtime trace must contain at least one span")

    def snapshot(self) -> dict[str, object]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "outcome": self.outcome,
            "spans": [
                {
                    "name": span.name,
                    "status": span.status,
                    "attributes": {
                        key: list(value) if isinstance(value, tuple) else value
                        for key, value in span.attributes.items()
                    },
                }
                for span in self.spans
            ],
        }


class LiveSpanRecorder(Protocol):
    """Vendor-neutral context manager for real operation timings."""

    def span(self, name: str) -> ContextManager[None]: ...


class TraceSink(Protocol):
    def write(self, trace: RuntimeTrace) -> None: ...


class InMemoryTraceSink:
    def __init__(self) -> None:
        self.traces: list[RuntimeTrace] = []

    def write(self, trace: RuntimeTrace) -> None:
        self.traces.append(trace)


class CompositeTraceSink:
    """Fan out one immutable runtime trace to multiple sinks."""

    def __init__(self, *sinks: TraceSink) -> None:
        if not sinks:
            raise ValueError("composite trace sink requires at least one sink")
        self._sinks = sinks

    def write(self, trace: RuntimeTrace) -> None:
        for sink in self._sinks:
            sink.write(trace)


class JsonlTraceSink:
    """Append traces locally without duplicating raw query/evidence payloads."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def write(self, trace: RuntimeTrace) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = trace.snapshot()
        snapshot["recorded_at"] = datetime.now(UTC).isoformat()
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, separators=(",", ":")) + "\n")
