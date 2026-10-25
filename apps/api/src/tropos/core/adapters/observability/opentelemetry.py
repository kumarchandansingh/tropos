"""OpenTelemetry adapter for completed Tropos runtime traces.

OBS-101A exports an already-completed RuntimeTrace retrospectively. The OTel
span timings therefore describe export time, not the original operation
duration. Tropos-measured latency remains available as an explicit attribute.
Live runtime spans belong to OBS-101B.
"""

from __future__ import annotations

from opentelemetry.trace import Status, StatusCode, Tracer

from tropos.core.application.observability.trace import RuntimeTrace, TraceSpan, TraceValue

_SAFE_ATTRIBUTE_KEYS = frozenset(
    {
        "failure_type",
        "gate_version",
        "group_count",
        "input_tokens",
        "label",
        "latency_ms",
        "model",
        "output_tokens",
        "prompt_version",
        "provider_id",
        "deployment_id",
        "reason",
        "result_count",
        "retrieval_limit",
        "runtime_config_fingerprint",
        "score_components",
        "scores",
        "strategy_version",
        "threshold",
        "top_score",
        "validation_status",
    }
)


def _otel_value(value: TraceValue) -> str | int | float | bool | tuple[str, ...]:
    if value is None:
        return "null"
    return value


def _safe_attributes(span: TraceSpan) -> dict[str, str | int | float | bool | tuple[str, ...]]:
    return {
        f"tropos.{key}": _otel_value(value)
        for key, value in span.attributes.items()
        if key in _SAFE_ATTRIBUTE_KEYS
    }


class OpenTelemetryTraceSink:
    """Map Tropos semantic trace records to vendor-neutral OTel spans."""

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def write(self, trace: RuntimeTrace) -> None:
        with self._tracer.start_as_current_span(
            "tropos.resolve",
            attributes={
                "tropos.trace_id": trace.trace_id,
                "tropos.outcome": trace.outcome,
                "tropos.mapping_mode": "retrospective",
            },
        ) as root:
            if trace.outcome == "RUNTIME_FAILED":
                root.set_status(Status(StatusCode.ERROR))

            for recorded_span in trace.spans:
                with self._tracer.start_as_current_span(
                    recorded_span.name,
                    attributes=_safe_attributes(recorded_span),
                ) as exported_span:
                    exported_span.set_attribute(
                        "tropos.recorded_status",
                        recorded_span.status,
                    )
                    if recorded_span.status == "ERROR":
                        exported_span.set_status(Status(StatusCode.ERROR))
