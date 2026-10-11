"""Resolve evidence-set and sufficiency decision contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from tropos.core.application.retrieval.models import RetrievedKnowledgeChunk
from tropos.core.domain.evidence import EvidenceRef


class SufficiencyLabel(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class SufficiencyFailureType(StrEnum):
    NONE = "NONE"
    MISSING_CRITICAL_FACT = "MISSING_CRITICAL_FACT"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    CONFLICTING_SUPPORT = "CONFLICTING_SUPPORT"
    NO_ANSWER_SUPPORT = "NO_ANSWER_SUPPORT"
    OTHER = "OTHER"


class SufficiencyValidationStatus(StrEnum):
    UNVALIDATED = "UNVALIDATED"
    HUMAN_CALIBRATED = "HUMAN_CALIBRATED"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    alias: str
    reference: EvidenceRef
    text: str
    retrieval_rank: int
    retrieval_score: float
    retrieval_strategy_version: str

    def __post_init__(self) -> None:
        if not self.alias.strip():
            raise ValueError("evidence alias must not be blank")
        if not self.text.strip():
            raise ValueError("evidence text must not be blank")
        if self.retrieval_rank < 1:
            raise ValueError("retrieval_rank must be positive")
        if not self.retrieval_strategy_version.strip():
            raise ValueError("retrieval_strategy_version must not be blank")


@dataclass(frozen=True, slots=True)
class EvidenceSet:
    evidence_set_id: str
    query: str
    items: tuple[EvidenceItem, ...]

    def __post_init__(self) -> None:
        if not self.evidence_set_id.strip():
            raise ValueError("evidence_set_id must not be blank")
        if not self.query.strip():
            raise ValueError("query must not be blank")
        if not self.items:
            raise ValueError("eligible evidence set must not be empty")
        aliases = tuple(item.alias for item in self.items)
        if len(aliases) != len(set(aliases)):
            raise ValueError("evidence aliases must be unique")
        chunk_ids = tuple(item.reference.chunk_id for item in self.items)
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("evidence set must not contain duplicate chunks")


@dataclass(frozen=True, slots=True)
class SufficiencyDecision:
    label: SufficiencyLabel
    failure_type: SufficiencyFailureType
    required_facts: tuple[str, ...]
    supported_facts: tuple[str, ...]
    missing_facts: tuple[str, ...]
    contradictions: tuple[str, ...]
    rationale: str
    validation_status: SufficiencyValidationStatus = SufficiencyValidationStatus.UNVALIDATED

    def __post_init__(self) -> None:
        for field_name, values in (
            ("required_facts", self.required_facts),
            ("supported_facts", self.supported_facts),
            ("missing_facts", self.missing_facts),
            ("contradictions", self.contradictions),
        ):
            if any(not value.strip() for value in values):
                raise ValueError(f"{field_name} must not contain blanks")
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates")
        if not self.rationale.strip():
            raise ValueError("rationale must not be blank")

        if self.label is SufficiencyLabel.SUFFICIENT:
            if self.failure_type is not SufficiencyFailureType.NONE:
                raise ValueError("SUFFICIENT decision must use failure type NONE")
            if self.missing_facts or self.contradictions:
                raise ValueError("SUFFICIENT decision cannot declare missing facts or contradictions")
        elif self.failure_type is SufficiencyFailureType.NONE:
            raise ValueError("INSUFFICIENT decision requires a failure type")


def evidence_set_from_retrieval(
    *,
    evidence_set_id: str,
    query: str,
    results: tuple[RetrievedKnowledgeChunk, ...],
) -> EvidenceSet:
    """Freeze already-governed retrieval output as eligible model context."""

    items: list[EvidenceItem] = []
    for index, result in enumerate(results, start=1):
        chunk = result.chunk
        reference = EvidenceRef(
            chunk_id=chunk.chunk_id,
            knowledge_id=chunk.knowledge_id,
            source_system=chunk.source_system,
            source_record_id=chunk.source_record_id,
            source_version=chunk.source_version,
            locator=(
                f"{chunk.source_system}:{chunk.source_record_id}@v{chunk.source_version}"
                f"#chars={chunk.start_offset}-{chunk.end_offset}"
            ),
            content_fingerprint=chunk.content_fingerprint,
        )
        items.append(
            EvidenceItem(
                alias=f"E{index}",
                reference=reference,
                text=chunk.text,
                retrieval_rank=result.rank,
                retrieval_score=result.score,
                retrieval_strategy_version=result.strategy_version,
            )
        )
    return EvidenceSet(evidence_set_id=evidence_set_id, query=query, items=tuple(items))
