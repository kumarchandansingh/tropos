"""Runtime retrieval gate kept independent from evaluation calibration code."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from tropos.core.application.retrieval.models import RetrievedKnowledgeChunk

_GATE_VERSION = "runtime-retrieval-gate-v1"


@dataclass(frozen=True, slots=True)
class RetrievalGateDecision:
    passed: bool
    reason: str
    result_count: int
    top_score: float | None
    threshold: float | None
    gate_version: str = _GATE_VERSION


def apply_retrieval_gate(
    results: tuple[RetrievedKnowledgeChunk, ...],
    *,
    threshold: float | None,
) -> RetrievalGateDecision:
    """Abstain on no eligible evidence and optionally enforce a supplied threshold."""

    if threshold is not None and not isfinite(threshold):
        raise ValueError("retrieval threshold must be finite")

    if not results:
        return RetrievalGateDecision(
            passed=False,
            reason="no_eligible_evidence",
            result_count=0,
            top_score=None,
            threshold=threshold,
        )

    top_score = results[0].score
    if threshold is not None and top_score < threshold:
        return RetrievalGateDecision(
            passed=False,
            reason="below_runtime_threshold",
            result_count=len(results),
            top_score=top_score,
            threshold=threshold,
        )

    return RetrievalGateDecision(
        passed=True,
        reason="eligible_evidence_available",
        result_count=len(results),
        top_score=top_score,
        threshold=threshold,
    )
