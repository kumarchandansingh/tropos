"""End-to-end Resolve question orchestration."""

from __future__ import annotations

from hashlib import sha256
from time import perf_counter
from contextlib import nullcontext
from typing import ContextManager, Protocol
from uuid import uuid4

from tropos.capabilities.resolve.application.evaluate_evidence_sufficiency import (
    JudgedSufficiency,
)
from tropos.capabilities.resolve.application.generate_grounded_answer import (
    CitationResolutionError,
    GeneratedGroundedAnswer,
)
from tropos.capabilities.resolve.domain.evidence_sufficiency import (
    EvidenceSet,
    SufficiencyLabel,
    evidence_set_from_retrieval,
)
from tropos.capabilities.resolve.domain.runtime import (
    ResolveOutcome,
    ResolveResult,
    RuntimeRequest,
)
from tropos.core.application.observability.trace import (
    LiveSpanRecorder,
    RuntimeTrace,
    TraceSink,
    TraceSpan,
)
from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.retrieval.abstention import apply_retrieval_gate
from tropos.core.application.retrieval.models import KnowledgeSearchRequest


class SufficiencyJudge(Protocol):
    def judge(self, evidence_set: EvidenceSet) -> JudgedSufficiency: ...


class GroundedAnswerGenerator(Protocol):
    def generate(self, evidence_set: EvidenceSet) -> GeneratedGroundedAnswer: ...


class ResolveQuestion:
    """Compose governed retrieval, sufficiency, generation, citations, and trace."""

    def __init__(
        self,
        *,
        retriever: KnowledgeChunkRetriever,
        sufficiency_judge: SufficiencyJudge,
        answer_generator: GroundedAnswerGenerator,
        trace_sink: TraceSink,
        live_spans: LiveSpanRecorder | None = None,
    ) -> None:
        self._retriever = retriever
        self._sufficiency_judge = sufficiency_judge
        self._answer_generator = answer_generator
        self._trace_sink = trace_sink
        self._live_spans = live_spans

    def _operation(self, name: str) -> ContextManager[None]:
        if self._live_spans is None:
            return nullcontext()
        return self._live_spans.span(name)

    def execute(self, request: RuntimeRequest) -> ResolveResult:
        with self._operation("resolve.request"):
            return self._execute_with_trace(request)

    def _execute_with_trace(self, request: RuntimeRequest) -> ResolveResult:
        trace_id = f"trace_{uuid4().hex}"
        runtime_config_fingerprint = sha256(
            (
                f"{self._retriever.strategy_version}|"
                f"limit={request.retrieval_limit}|"
                f"threshold={request.retrieval_threshold!r}"
            ).encode()
        ).hexdigest()
        spans: list[TraceSpan] = [
            TraceSpan(
                name="resolve.request",
                status="OK",
                attributes={
                    "request_id": request.request_id,
                    "query_fingerprint": sha256(request.query.encode()).hexdigest(),
                    "tenant_id": request.access.tenant_id,
                    "group_count": len(request.access.groups),
                    "retrieval_limit": request.retrieval_limit,
                    "runtime_config_fingerprint": runtime_config_fingerprint,
                },
            )
        ]

        retrieval_started = perf_counter()
        try:
            with self._operation("resolve.retrieval"):
                results = self._retriever.search(
                KnowledgeSearchRequest(
                    query=request.query,
                    access=request.access,
                    limit=request.retrieval_limit,
                )
                )
        except (ValueError, RuntimeError, OSError) as exc:
            spans.append(
                TraceSpan(
                    name="resolve.retrieval",
                    status="ERROR",
                    attributes={"error_type": type(exc).__name__},
                )
            )
            self._fail_trace(trace_id, request, spans)
            raise
        spans.append(
            TraceSpan(
                name="resolve.retrieval",
                status="OK",
                attributes={
                    "strategy_version": self._retriever.strategy_version,
                    "latency_ms": round((perf_counter() - retrieval_started) * 1000, 3),
                    "result_count": len(results),
                    "chunk_ids": tuple(result.chunk.chunk_id for result in results),
                    "ranks": tuple(str(result.rank) for result in results),
                    "scores": tuple(f"{result.score:.17g}" for result in results),
                    "score_components": tuple(
                        "|".join(
                            f"{component.strategy_version}@{component.rank}={component.score:.17g}"
                            for component in result.score_components
                        )
                        for result in results
                    ),
                },
            )
        )

        gate = apply_retrieval_gate(results, threshold=request.retrieval_threshold)
        spans.append(
            TraceSpan(
                name="resolve.retrieval_gate",
                status="OK" if gate.passed else "ABSTAINED",
                attributes={
                    "gate_version": gate.gate_version,
                    "reason": gate.reason,
                    "threshold": gate.threshold,
                    "top_score": gate.top_score,
                },
            )
        )
        if not gate.passed:
            result = ResolveResult(
                trace_id=trace_id,
                outcome=ResolveOutcome.RETRIEVAL_ABSTAINED,
                abstention_reason=gate.reason,
            )
            self._finish_trace(trace_id, request, result, spans)
            return result

        evidence_set = evidence_set_from_retrieval(
            evidence_set_id=f"evidence_{trace_id}",
            query=request.query,
            results=results,
        )
        spans.append(
            TraceSpan(
                name="resolve.evidence_set",
                status="OK",
                attributes={
                    "evidence_set_id": evidence_set.evidence_set_id,
                    "evidence_aliases": tuple(item.alias for item in evidence_set.items),
                    "chunk_ids": tuple(item.reference.chunk_id for item in evidence_set.items),
                },
            )
        )

        try:
            with self._operation("resolve.sufficiency"):
                judged = self._sufficiency_judge.judge(evidence_set)
        except (ValueError, RuntimeError, OSError) as exc:
            spans.append(
                TraceSpan(
                    name="resolve.sufficiency",
                    status="ERROR",
                    attributes={"error_type": type(exc).__name__},
                )
            )
            self._fail_trace(trace_id, request, spans)
            raise
        decision = judged.decision
        spans.append(
            TraceSpan(
                name="resolve.sufficiency",
                status="OK",
                attributes={
                    "label": decision.label.value,
                    "failure_type": decision.failure_type.value,
                    "validation_status": decision.validation_status.value,
                    "provider_id": judged.invocation.provider_id,
                    "deployment_id": judged.invocation.deployment_id,
                    "model": judged.invocation.model_identifier,
                    "prompt_version": judged.invocation.prompt_version,
                    "latency_ms": judged.invocation.latency_ms,
                    "input_tokens": judged.invocation.input_tokens,
                    "output_tokens": judged.invocation.output_tokens,
                },
            )
        )
        if decision.label is SufficiencyLabel.INSUFFICIENT:
            result = ResolveResult(
                trace_id=trace_id,
                outcome=ResolveOutcome.EVIDENCE_INSUFFICIENT,
                evidence_set=evidence_set,
                sufficiency=decision,
                abstention_reason=decision.failure_type.value,
            )
            self._finish_trace(trace_id, request, result, spans)
            return result

        try:
            with self._operation("resolve.generation"):
                generated = self._answer_generator.generate(evidence_set)
        except CitationResolutionError as exc:
            spans.append(
                TraceSpan(
                    name="resolve.citation_validation",
                    status="ERROR",
                    attributes={"error_type": type(exc).__name__},
                )
            )
            self._fail_trace(trace_id, request, spans)
            raise
        except (ValueError, RuntimeError, OSError) as exc:
            spans.append(
                TraceSpan(
                    name="resolve.generation",
                    status="ERROR",
                    attributes={"error_type": type(exc).__name__},
                )
            )
            self._fail_trace(trace_id, request, spans)
            raise
        spans.append(
            TraceSpan(
                name="resolve.generation",
                status="OK",
                attributes={
                    "provider_id": generated.invocation.provider_id,
                    "deployment_id": generated.invocation.deployment_id,
                    "model": generated.invocation.model_identifier,
                    "prompt_version": generated.invocation.prompt_version,
                    "latency_ms": generated.invocation.latency_ms,
                    "input_tokens": generated.invocation.input_tokens,
                    "output_tokens": generated.invocation.output_tokens,
                },
            )
        )
        spans.append(
            TraceSpan(
                name="resolve.citation_validation",
                status="OK",
                attributes={
                    "citation_aliases": generated.answer.citation_aliases,
                    "resolved_chunk_ids": tuple(
                        citation.chunk_id for citation in generated.answer.citations
                    ),
                },
            )
        )
        result = ResolveResult(
            trace_id=trace_id,
            outcome=ResolveOutcome.ANSWERED,
            evidence_set=evidence_set,
            sufficiency=decision,
            answer=generated.answer,
        )
        self._finish_trace(trace_id, request, result, spans)
        return result

    def _fail_trace(
        self,
        trace_id: str,
        request: RuntimeRequest,
        spans: list[TraceSpan],
    ) -> None:
        self._trace_sink.write(
            RuntimeTrace(
                trace_id=trace_id,
                request_id=request.request_id,
                outcome="RUNTIME_FAILED",
                spans=tuple(spans),
            )
        )

    def _finish_trace(
        self,
        trace_id: str,
        request: RuntimeRequest,
        result: ResolveResult,
        spans: list[TraceSpan],
    ) -> None:
        self._trace_sink.write(
            RuntimeTrace(
                trace_id=trace_id,
                request_id=request.request_id,
                outcome=result.outcome.value,
                spans=tuple(spans),
            )
        )
