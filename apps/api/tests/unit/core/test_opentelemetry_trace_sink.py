from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from tropos.core.adapters.observability.opentelemetry import OpenTelemetryTraceSink
from tropos.core.application.observability.trace import RuntimeTrace, TraceSpan


def _exporter_and_sink() -> tuple[InMemorySpanExporter, OpenTelemetryTraceSink]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter, OpenTelemetryTraceSink(provider.get_tracer("tropos.tests"))


def test_runtime_trace_maps_to_one_parent_with_semantic_children() -> None:
    exporter, sink = _exporter_and_sink()
    sink.write(
        RuntimeTrace(
            trace_id="trace-1",
            request_id="request-1",
            outcome="ANSWERED",
            spans=(
                TraceSpan(
                    name="resolve.retrieval",
                    status="OK",
                    attributes={
                        "strategy_version": "hybrid_rrf_v1",
                        "result_count": 5,
                        "latency_ms": 61.2,
                    },
                ),
                TraceSpan(
                    name="resolve.generation",
                    status="OK",
                    attributes={
                        "model": "openai/gpt-oss-120b",
                        "output_tokens": 312,
                    },
                ),
            ),
        )
    )

    spans = exporter.get_finished_spans()
    assert tuple(span.name for span in spans) == (
        "resolve.retrieval",
        "resolve.generation",
        "tropos.resolve",
    )
    parent = spans[-1]
    assert parent.attributes["tropos.mapping_mode"] == "retrospective"
    assert parent.attributes["tropos.outcome"] == "ANSWERED"
    assert all(span.parent is not None for span in spans[:-1])
    assert all(span.parent.span_id == parent.context.span_id for span in spans[:-1])

    retrieval = spans[0]
    assert retrieval.attributes["tropos.strategy_version"] == "hybrid_rrf_v1"
    assert retrieval.attributes["tropos.result_count"] == 5
    assert retrieval.attributes["tropos.latency_ms"] == 61.2


def test_error_status_is_preserved_without_exporting_exception_message() -> None:
    exporter, sink = _exporter_and_sink()
    sink.write(
        RuntimeTrace(
            trace_id="trace-2",
            request_id="request-2",
            outcome="RUNTIME_FAILED",
            spans=(
                TraceSpan(
                    name="resolve.retrieval",
                    status="ERROR",
                    attributes={"error_type": "RuntimeError"},
                ),
            ),
        )
    )

    child, parent = exporter.get_finished_spans()
    assert child.status.status_code is StatusCode.ERROR
    assert parent.status.status_code is StatusCode.ERROR
    assert child.attributes["tropos.recorded_status"] == "ERROR"


def test_governed_identifiers_and_content_are_not_exported() -> None:
    exporter, sink = _exporter_and_sink()
    secret = "SENSITIVE-RAW-EVIDENCE-DO-NOT-EXPORT"
    sink.write(
        RuntimeTrace(
            trace_id="trace-safe",
            request_id="request-sensitive",
            outcome="ANSWERED",
            spans=(
                TraceSpan(
                    name="resolve.request",
                    status="OK",
                    attributes={
                        "tenant_id": "customer-secret",
                        "request_id": "request-sensitive",
                        "query_fingerprint": "abc123",
                        "group_count": 2,
                    },
                ),
                TraceSpan(
                    name="resolve.evidence_set",
                    status="OK",
                    attributes={
                        "evidence_set_id": "evidence-secret",
                        "chunk_ids": ("chunk-secret",),
                        "evidence_aliases": (secret,),
                    },
                ),
            ),
        )
    )

    serialized = str([(span.name, dict(span.attributes)) for span in exporter.get_finished_spans()])
    assert secret not in serialized
    assert "customer-secret" not in serialized
    assert "request-sensitive" not in serialized
    assert "evidence-secret" not in serialized
    assert "chunk-secret" not in serialized
    assert "tropos.group_count" in serialized
