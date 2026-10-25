"""Optional, locally configured OpenTelemetry runtime.

No network exporter is installed or enabled by this configuration.
Set TROPOS_OTEL_CONSOLE=1 to output live spans to standard output.
"""

from __future__ import annotations

import os

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from tropos.core.adapters.observability.live_opentelemetry import (
    OpenTelemetryLiveSpanRecorder,
)


def build_live_span_recorder() -> OpenTelemetryLiveSpanRecorder | None:
    if os.environ.get("TROPOS_OTEL_CONSOLE") != "1":
        return None
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    return OpenTelemetryLiveSpanRecorder(provider.get_tracer("tropos.resolve"))
