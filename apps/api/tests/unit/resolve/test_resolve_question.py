from __future__ import annotations

from hashlib import sha256

import pytest

from tropos.capabilities.resolve.application.evaluate_evidence_sufficiency import (
    JudgedSufficiency,
)
from tropos.capabilities.resolve.application.generate_grounded_answer import (
    CitationResolutionError,
    GeneratedGroundedAnswer,
)
from tropos.capabilities.resolve.application.resolve_question import ResolveQuestion
from tropos.capabilities.resolve.domain.evidence_sufficiency import (
    EvidenceSet,
    SufficiencyDecision,
    SufficiencyFailureType,
    SufficiencyLabel,
)
from tropos.capabilities.resolve.domain.runtime import (
    GroundedAnswer,
    ResolveOutcome,
    RuntimeRequest,
)
from tropos.core.application.observability.trace import InMemoryTraceSink
from tropos.core.application.ports.llm import LLMInvocationMetadata
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
    RetrievalScoreComponent,
    RetrievedKnowledgeChunk,
)
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge_chunk import KnowledgeChunk


def _metadata(prompt: str) -> LLMInvocationMetadata:
    return LLMInvocationMetadata(
        provider_id="fake",
        connection_id="fake",
        deployment_id="fake",
        model_identifier="fake-model",
        prompt_version=prompt,
        latency_ms=1.0,
        input_tokens=10,
        output_tokens=4,
    )


def _result(
    text: str = "Restart after certificate rotation.",
    *,
    score_components: tuple[RetrievalScoreComponent, ...] = (),
) -> RetrievedKnowledgeChunk:
    fingerprint = sha256(text.encode()).hexdigest()
    chunk = KnowledgeChunk(
        chunk_id="chunk-1",
        knowledge_id="knowledge-1",
        source_system="manual",
        source_record_id="runbook.md",
        source_version="1",
        document_title="Runbook",
        sequence_number=0,
        text=text,
        start_offset=0,
        end_offset=len(text),
        content_fingerprint=fingerprint,
        ingestion_fingerprint="a" * 64,
        normalized_content_fingerprint="b" * 64,
        normalization_strategy_version="norm-v1",
        access_policy=AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT),
        strategy_version="chunk-v1",
    )
    return RetrievedKnowledgeChunk(
        chunk=chunk,
        rank=1,
        score=0.9,
        strategy_version="retrieval-v1",
        score_components=score_components,
    )


class StaticRetriever:
    strategy_version = "retrieval-v1"

    def __init__(self, results: tuple[RetrievedKnowledgeChunk, ...]) -> None:
        self.results = results
        self.requests: list[KnowledgeSearchRequest] = []

    def search(self, request: KnowledgeSearchRequest) -> tuple[RetrievedKnowledgeChunk, ...]:
        self.requests.append(request)
        return self.results


class StaticJudge:
    def __init__(self, decision: SufficiencyDecision) -> None:
        self.decision = decision
        self.calls = 0

    def judge(self, evidence_set: EvidenceSet) -> JudgedSufficiency:
        self.calls += 1
        return JudgedSufficiency(
            evidence_set_id=evidence_set.evidence_set_id,
            decision=self.decision,
            invocation=_metadata("sufficiency-v1"),
        )


class FailingJudge:
    def judge(self, evidence_set: EvidenceSet) -> JudgedSufficiency:
        raise AssertionError("judge must not be called")


class StaticGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, evidence_set: EvidenceSet) -> GeneratedGroundedAnswer:
        self.calls += 1
        item = evidence_set.items[0]
        return GeneratedGroundedAnswer(
            answer=GroundedAnswer(
                text="Restart the device after rotation.",
                citation_aliases=(item.alias,),
                citations=(item.reference,),
            ),
            invocation=_metadata("generation-v1"),
        )


class FailingGenerator:
    def generate(self, evidence_set: EvidenceSet) -> GeneratedGroundedAnswer:
        raise AssertionError("generator must not be called")


class CitationFailingGenerator:
    def generate(self, evidence_set: EvidenceSet) -> GeneratedGroundedAnswer:
        raise CitationResolutionError("unknown citation")


def _request() -> RuntimeRequest:
    return RuntimeRequest(
        request_id="request-1",
        query="What should I do after certificate rotation?",
        access=RetrievalAccessContext(tenant_id="tenant-a"),
    )


def test_no_evidence_abstains_before_any_model_call() -> None:
    sink = InMemoryTraceSink()
    runtime = ResolveQuestion(
        retriever=StaticRetriever(()),
        sufficiency_judge=FailingJudge(),
        answer_generator=FailingGenerator(),
        trace_sink=sink,
    )

    result = runtime.execute(_request())

    assert result.outcome is ResolveOutcome.RETRIEVAL_ABSTAINED
    assert result.abstention_reason == "no_eligible_evidence"
    assert len(sink.traces) == 1
    assert sink.traces[0].outcome == "RETRIEVAL_ABSTAINED"


def test_insufficient_evidence_never_calls_generation() -> None:
    sink = InMemoryTraceSink()
    judge = StaticJudge(
        SufficiencyDecision(
            label=SufficiencyLabel.INSUFFICIENT,
            failure_type=SufficiencyFailureType.MISSING_CRITICAL_FACT,
            required_facts=("firmware version",),
            supported_facts=(),
            missing_facts=("firmware version",),
            contradictions=(),
            rationale="Required diagnostic fact is absent.",
        )
    )
    runtime = ResolveQuestion(
        retriever=StaticRetriever((_result(),)),
        sufficiency_judge=judge,
        answer_generator=FailingGenerator(),
        trace_sink=sink,
    )

    result = runtime.execute(_request())

    assert result.outcome is ResolveOutcome.EVIDENCE_INSUFFICIENT
    assert result.sufficiency is not None
    assert result.sufficiency.missing_facts == ("firmware version",)
    assert len(sink.traces) == 1


def test_sufficient_evidence_generates_answer_and_resolves_citation() -> None:
    sink = InMemoryTraceSink()
    judge = StaticJudge(
        SufficiencyDecision(
            label=SufficiencyLabel.SUFFICIENT,
            failure_type=SufficiencyFailureType.NONE,
            required_facts=("post-rotation action",),
            supported_facts=("restart the device",),
            missing_facts=(),
            contradictions=(),
            rationale="Required action is present.",
        )
    )
    generator = StaticGenerator()
    runtime = ResolveQuestion(
        retriever=StaticRetriever((_result(),)),
        sufficiency_judge=judge,
        answer_generator=generator,
        trace_sink=sink,
    )

    result = runtime.execute(_request())

    assert result.outcome is ResolveOutcome.ANSWERED
    assert result.answer is not None
    assert result.answer.citations[0].chunk_id == "chunk-1"
    assert generator.calls == 1
    assert len(sink.traces) == 1
    span_names = tuple(span.name for span in sink.traces[0].spans)
    assert span_names == (
        "resolve.request",
        "resolve.retrieval",
        "resolve.retrieval_gate",
        "resolve.evidence_set",
        "resolve.sufficiency",
        "resolve.generation",
        "resolve.citation_validation",
    )


def test_trace_does_not_duplicate_raw_query_or_evidence_text() -> None:
    sink = InMemoryTraceSink()
    secret_text = "SENSITIVE-RAW-EVIDENCE-DO-NOT-TRACE"
    query = "SENSITIVE-QUERY-DO-NOT-TRACE"
    judge = StaticJudge(
        SufficiencyDecision(
            label=SufficiencyLabel.INSUFFICIENT,
            failure_type=SufficiencyFailureType.NO_ANSWER_SUPPORT,
            required_facts=("answer",),
            supported_facts=(),
            missing_facts=("answer",),
            contradictions=(),
            rationale="No answer-bearing support.",
        )
    )
    runtime = ResolveQuestion(
        retriever=StaticRetriever((_result(secret_text),)),
        sufficiency_judge=judge,
        answer_generator=FailingGenerator(),
        trace_sink=sink,
    )
    request = RuntimeRequest(
        request_id="request-sensitive",
        query=query,
        access=RetrievalAccessContext(tenant_id="tenant-a"),
    )

    runtime.execute(request)

    snapshot = str(sink.traces[0].snapshot())
    assert secret_text not in snapshot
    assert query not in snapshot


def test_citation_failure_is_traced_as_runtime_failure() -> None:
    sink = InMemoryTraceSink()
    judge = StaticJudge(
        SufficiencyDecision(
            label=SufficiencyLabel.SUFFICIENT,
            failure_type=SufficiencyFailureType.NONE,
            required_facts=("action",),
            supported_facts=("restart",),
            missing_facts=(),
            contradictions=(),
            rationale="Evidence is sufficient.",
        )
    )
    runtime = ResolveQuestion(
        retriever=StaticRetriever((_result(),)),
        sufficiency_judge=judge,
        answer_generator=CitationFailingGenerator(),
        trace_sink=sink,
    )

    with pytest.raises(CitationResolutionError):
        runtime.execute(_request())

    assert len(sink.traces) == 1
    assert sink.traces[0].outcome == "RUNTIME_FAILED"
    assert sink.traces[0].spans[-1].name == "resolve.citation_validation"
    assert sink.traces[0].spans[-1].status == "ERROR"


def test_trace_preserves_hybrid_component_rank_provenance() -> None:
    sink = InMemoryTraceSink()
    result = _result(
        score_components=(
            RetrievalScoreComponent(
                strategy_version="bm25-v1",
                rank=2,
                score=4.2,
            ),
            RetrievalScoreComponent(
                strategy_version="dense-v1",
                rank=1,
                score=0.91,
            ),
        )
    )
    judge = StaticJudge(
        SufficiencyDecision(
            label=SufficiencyLabel.INSUFFICIENT,
            failure_type=SufficiencyFailureType.NO_ANSWER_SUPPORT,
            required_facts=("answer",),
            supported_facts=(),
            missing_facts=("answer",),
            contradictions=(),
            rationale="No answer support.",
        )
    )
    runtime = ResolveQuestion(
        retriever=StaticRetriever((result,)),
        sufficiency_judge=judge,
        answer_generator=FailingGenerator(),
        trace_sink=sink,
    )

    runtime.execute(_request())

    retrieval_span = next(span for span in sink.traces[0].spans if span.name == "resolve.retrieval")
    assert retrieval_span.attributes["ranks"] == ("1",)
    assert retrieval_span.attributes["score_components"] == (
        "bm25-v1@2=4.2000000000000002|dense-v1@1=0.91000000000000003",
    )
