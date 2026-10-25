"""Opt-in, vendor-neutral OpenTelemetry runtime for Tropos Resolve.

Default: no network exporter and no console output.
Console: TROPOS_OTEL_CONSOLE=1
OTLP/HTTP: TROPOS_OTEL_OTLP_ENDPOINT=http://127.0.0.1:4318/v1/traces

Raw questions, evidence, answers, tenant IDs, and credentials are never attached
to live spans. OTLP export is opt-in; it requires the OTLP HTTP exporter package.
"""

from __future__ import annotations

import os

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from tropos.core.adapters.observability.live_opentelemetry import (
    OpenTelemetryLiveSpanRecorder,
)


def build_live_span_recorder() -> OpenTelemetryLiveSpanRecorder | None:
    """Configure one exporter, with explicit opt-in and no vendor coupling."""
    endpoint = os.environ.get("TROPOS_OTEL_OTLP_ENDPOINT", "").strip()
    console = os.environ.get("TROPOS_OTEL_CONSOLE") == "1"

    if not endpoint and not console:
        return None

    if endpoint and not (endpoint.startswith("http://") or endpoint.startswith("https://")):
        raise ValueError("TROPOS_OTEL_OTLP_ENDPOINT must be an HTTP(S) URL")

    provider = TracerProvider(resource=Resource.create({"service.name": "tropos-api"}))
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "OTLP export requires opentelemetry-exporter-otlp-proto-http. "
                "Install the optional exporter before enabling TROPOS_OTEL_OTLP_ENDPOINT."
            ) from exc
        # OTLPSpanExporter supports headers via the standard OTEL_EXPORTER_OTLP_*
        # environment variables. Never emit or log their values.
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    if console:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    return OpenTelemetryLiveSpanRecorder(provider.get_tracer("tropos.resolve"))
