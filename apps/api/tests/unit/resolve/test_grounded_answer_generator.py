from __future__ import annotations

import pytest
from pydantic import BaseModel

from tropos.capabilities.resolve.application.generate_grounded_answer import (
    LLMGroundedAnswerGenerator,
)
from tropos.capabilities.resolve.domain.evidence_sufficiency import (
    EvidenceItem,
    EvidenceSet,
)
from tropos.core.adapters.llm.fake import FakeLLM
from tropos.core.domain.evidence import EvidenceRef


class AnswerFixture(BaseModel):
    answer: str
    citations: list[str]


def _evidence() -> EvidenceSet:
    return EvidenceSet(
        evidence_set_id="evidence-1",
        query="What is the action?",
        items=(
            EvidenceItem(
                alias="E1",
                reference=EvidenceRef(
                    chunk_id="chunk-1",
                    knowledge_id="knowledge-1",
                    source_system="manual",
                    source_record_id="runbook.md",
                    source_version="1",
                    locator="manual:runbook.md@v1#chars=0-12",
                    content_fingerprint="a" * 64,
                ),
                text="Restart it.",
                retrieval_rank=1,
                retrieval_score=0.9,
                retrieval_strategy_version="retrieval-v1",
            ),
        ),
    )


def test_generator_resolves_alias_to_exact_evidence_ref() -> None:
    generator = LLMGroundedAnswerGenerator(
        FakeLLM(structured_outputs=(AnswerFixture(answer="Restart it.", citations=["E1"]),))
    )

    result = generator.generate(_evidence())

    assert result.answer.citation_aliases == ("E1",)
    assert result.answer.citations[0].chunk_id == "chunk-1"


def test_generator_fails_closed_on_unknown_citation() -> None:
    generator = LLMGroundedAnswerGenerator(
        FakeLLM(structured_outputs=(AnswerFixture(answer="Invented answer.", citations=["E99"]),))
    )

    with pytest.raises(ValueError, match="unknown evidence citation"):
        generator.generate(_evidence())
