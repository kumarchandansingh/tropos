from __future__ import annotations

from hashlib import sha256

import pytest
from pydantic import BaseModel

from tropos.capabilities.resolve.application.evaluate_evidence_sufficiency import (
    LLMEvidenceSufficiencyJudge,
)
from tropos.capabilities.resolve.domain.evidence_sufficiency import (
    SufficiencyFailureType,
    SufficiencyLabel,
    SufficiencyValidationStatus,
    evidence_set_from_retrieval,
)
from tropos.core.adapters.llm.fake import FakeLLM
from tropos.core.application.retrieval.models import RetrievedKnowledgeChunk
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge_chunk import KnowledgeChunk


class SufficiencyFixture(BaseModel):
    label: str
    failure_type: str
    required_facts: list[str]
    supported_facts: list[str]
    missing_facts: list[str]
    contradictions: list[str]
    rationale: str


def _retrieved(text: str = "Restart the device after certificate rotation.") -> tuple[RetrievedKnowledgeChunk, ...]:
    fingerprint = sha256(text.encode()).hexdigest()
    chunk = KnowledgeChunk(
        chunk_id="chunk-1",
        knowledge_id="knowledge-1",
        source_system="manual",
        source_record_id="device.md",
        source_version="3",
        document_title="Device runbook",
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
    return (
        RetrievedKnowledgeChunk(
            chunk=chunk,
            rank=1,
            score=0.9,
            strategy_version="retrieval-v1",
        ),
    )


def test_freezes_governed_retrieval_as_evidence_set() -> None:
    evidence = evidence_set_from_retrieval(
        evidence_set_id="es-1",
        query="What should I do after rotation?",
        results=_retrieved(),
    )

    assert evidence.items[0].alias == "E1"
    assert evidence.items[0].reference.chunk_id == "chunk-1"
    assert evidence.items[0].reference.locator.endswith("#chars=0-46")


def test_sufficiency_judge_returns_unvalidated_operational_decision() -> None:
    fake = FakeLLM(
        structured_outputs=(
            SufficiencyFixture(
                label="SUFFICIENT",
                failure_type="NONE",
                required_facts=["post-rotation action"],
                supported_facts=["restart the device"],
                missing_facts=[],
                contradictions=[],
                rationale="The evidence directly states the required action.",
            ),
        )
    )
    evidence = evidence_set_from_retrieval(
        evidence_set_id="es-1",
        query="What should I do after rotation?",
        results=_retrieved(),
    )

    result = LLMEvidenceSufficiencyJudge(fake).judge(evidence)

    assert result.decision.label is SufficiencyLabel.SUFFICIENT
    assert result.decision.failure_type is SufficiencyFailureType.NONE
    assert result.decision.validation_status is SufficiencyValidationStatus.UNVALIDATED
    assert result.invocation.provider_id == "fake"


def test_sufficiency_judge_surfaces_missing_facts() -> None:
    fake = FakeLLM(
        structured_outputs=(
            SufficiencyFixture(
                label="INSUFFICIENT",
                failure_type="MISSING_CRITICAL_FACT",
                required_facts=["certificate chain", "firmware version"],
                supported_facts=["rotation occurred"],
                missing_facts=["certificate chain", "firmware version"],
                contradictions=[],
                rationale="Two required diagnostic facts are absent.",
            ),
        )
    )
    evidence = evidence_set_from_retrieval(
        evidence_set_id="es-2",
        query="Why did activation fail?",
        results=_retrieved("Certificate rotation occurred."),
    )

    result = LLMEvidenceSufficiencyJudge(fake).judge(evidence)

    assert result.decision.label is SufficiencyLabel.INSUFFICIENT
    assert result.decision.missing_facts == ("certificate chain", "firmware version")


def test_sufficient_decision_cannot_hide_missing_facts() -> None:
    fake = FakeLLM(
        structured_outputs=(
            SufficiencyFixture(
                label="SUFFICIENT",
                failure_type="NONE",
                required_facts=["firmware version"],
                supported_facts=[],
                missing_facts=["firmware version"],
                contradictions=[],
                rationale="Incorrect provider output.",
            ),
        )
    )
    evidence = evidence_set_from_retrieval(
        evidence_set_id="es-3",
        query="Why?",
        results=_retrieved(),
    )

    with pytest.raises(ValueError, match="cannot declare missing facts"):
        LLMEvidenceSufficiencyJudge(fake).judge(evidence)
