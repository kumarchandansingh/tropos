"""Live OpenTelemetry spans emitted while Resolve operations execute.

Only operation names are exported. Raw request/evidence/answer content and
customer identifiers never enter the telemetry path.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Tracer


class OpenTelemetryLiveSpanRecorder:
    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        with self._tracer.start_as_current_span(
            name,
            attributes={"tropos.mapping_mode": "live"},
            record_exception=False,
        ) as current:
            try:
                yield
            except Exception as exc:
                from opentelemetry.trace import Status, StatusCode

                current.set_status(Status(StatusCode.ERROR))
                current.set_attribute("tropos.error_type", type(exc).__name__)
                raise
