"""Resolve request/result contracts for the end-to-end runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from tropos.capabilities.resolve.domain.evidence_sufficiency import (
    EvidenceSet,
    SufficiencyDecision,
)
from tropos.core.application.retrieval.models import RetrievalAccessContext
from tropos.core.domain.evidence import EvidenceRef


class ResolveOutcome(StrEnum):
    ANSWERED = "ANSWERED"
    RETRIEVAL_ABSTAINED = "RETRIEVAL_ABSTAINED"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    request_id: str
    query: str
    access: RetrievalAccessContext
    retrieval_limit: int = 5
    retrieval_threshold: float | None = None

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id must not be blank")
        if not self.query.strip():
            raise ValueError("query must not be blank")
        if not 1 <= self.retrieval_limit <= 100:
            raise ValueError("retrieval_limit must be between 1 and 100")


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    text: str
    citation_aliases: tuple[str, ...]
    citations: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("answer text must not be blank")
        if not self.citation_aliases:
            raise ValueError("grounded answer requires at least one citation")
        if len(self.citation_aliases) != len(self.citations):
            raise ValueError("citation aliases and resolved citations must align")
        if len(self.citation_aliases) != len(set(self.citation_aliases)):
            raise ValueError("citation aliases must not contain duplicates")


@dataclass(frozen=True, slots=True)
class ResolveResult:
    trace_id: str
    outcome: ResolveOutcome
    evidence_set: EvidenceSet | None = None
    sufficiency: SufficiencyDecision | None = None
    answer: GroundedAnswer | None = None
    abstention_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.trace_id.strip():
            raise ValueError("trace_id must not be blank")
        if self.outcome is ResolveOutcome.ANSWERED:
            if self.evidence_set is None or self.sufficiency is None or self.answer is None:
                raise ValueError("ANSWERED result requires evidence, sufficiency, and answer")
            if self.abstention_reason is not None:
                raise ValueError("ANSWERED result cannot contain abstention reason")
        else:
            if self.answer is not None:
                raise ValueError("abstained result cannot contain an answer")
            if not self.abstention_reason:
                raise ValueError("abstained result requires a reason")
