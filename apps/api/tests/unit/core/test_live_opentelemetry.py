from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from tropos.capabilities.resolve.application.evaluate_evidence_sufficiency import JudgedSufficiency
from tropos.capabilities.resolve.application.generate_grounded_answer import GeneratedGroundedAnswer
from tropos.capabilities.resolve.application.resolve_question import ResolveQuestion
from tropos.capabilities.resolve.domain.evidence_sufficiency import EvidenceSet
from tropos.capabilities.resolve.domain.runtime import ResolveOutcome, RuntimeRequest
from tropos.core.adapters.observability.live_opentelemetry import (
    OpenTelemetryLiveSpanRecorder,
)
from tropos.core.application.observability.trace import InMemoryTraceSink
from tropos.core.application.retrieval.models import RetrievalAccessContext


class EmptyRetriever:
    strategy_version = "test-empty"

    def search(self, request: object) -> tuple[()]:
        return ()


class FailingRetriever:
    strategy_version = "test-failing"

    def search(self, request: object) -> tuple[()]:
        raise RuntimeError("sensitive retrieval failure")


class NeverCall:
    def judge(self, evidence_set: EvidenceSet) -> JudgedSufficiency:
        raise AssertionError("must not run")

    def generate(self, evidence_set: EvidenceSet) -> GeneratedGroundedAnswer:
        raise AssertionError("must not run")


def _runtime(
    retriever: EmptyRetriever | FailingRetriever,
) -> tuple[ResolveQuestion, InMemoryTraceSink, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    sink = InMemoryTraceSink()
    runtime = ResolveQuestion(
        retriever=retriever,
        sufficiency_judge=NeverCall(),
        answer_generator=NeverCall(),
        trace_sink=sink,
        live_spans=OpenTelemetryLiveSpanRecorder(provider.get_tracer("tropos.test")),
    )
    return runtime, sink, exporter


def _request() -> RuntimeRequest:
    return RuntimeRequest(
        request_id="sensitive-request-id",
        query="SENSITIVE-QUERY-DO-NOT-TRACE",
        access=RetrievalAccessContext(tenant_id="sensitive-tenant"),
    )


def test_no_evidence_creates_real_nested_spans_and_preserves_jsonl_contract() -> None:
    runtime, sink, exporter = _runtime(EmptyRetriever())
    result = runtime.execute(_request())
    assert result.outcome is ResolveOutcome.RETRIEVAL_ABSTAINED
    assert sink.traces[0].outcome == "RETRIEVAL_ABSTAINED"
    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["resolve.retrieval", "resolve.request"]
    child, parent = spans
    assert child.parent is not None
    assert child.parent.span_id == parent.context.span_id
    assert parent.end_time is not None and parent.start_time is not None
    assert parent.end_time >= parent.start_time
    assert child.end_time is not None and child.start_time is not None
    assert child.end_time >= child.start_time
    serialized = str([(span.name, dict(span.attributes or {})) for span in spans])
    assert "SENSITIVE-QUERY-DO-NOT-TRACE" not in serialized
    assert "sensitive-tenant" not in serialized
    assert "sensitive-request-id" not in serialized


def test_retrieval_failure_is_error_span_without_exception_message() -> None:
    runtime, sink, exporter = _runtime(FailingRetriever())
    with pytest.raises(RuntimeError, match="sensitive retrieval failure"):
        runtime.execute(_request())
    assert sink.traces[0].outcome == "RUNTIME_FAILED"
    child, parent = exporter.get_finished_spans()
    assert child.status.status_code is StatusCode.ERROR
    assert parent.status.status_code is StatusCode.ERROR
    assert child.attributes is not None
    assert child.attributes["tropos.error_type"] == "RuntimeError"
    assert "sensitive retrieval failure" not in str(child.attributes)
