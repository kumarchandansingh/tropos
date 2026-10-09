"""Deterministic contract tests; no model credentials or network calls required."""

from hashlib import sha256
from typing import Any

import pytest

from tropos.capabilities.training.langchain_extractor import LangChainProcedureExtractor
from tropos.capabilities.training.procedure import EvidenceExcerpt, GapKind
from tropos.core.domain.evidence import EvidenceRef


class FakeStructuredModel:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.messages: Any = None

    def invoke(self, messages: Any) -> dict[str, Any]:
        self.messages = messages
        return self.response


class FakeModel:
    def __init__(self, response: dict[str, Any]) -> None:
        self.structured = FakeStructuredModel(response)

    def with_structured_output(self, schema: Any) -> FakeStructuredModel:
        assert schema is not None
        return self.structured


def evidence() -> tuple[EvidenceExcerpt, ...]:
    text = "Submit an eligible item"
    return (
        EvidenceExcerpt(
            reference=EvidenceRef(
                chunk_id="uat-1",
                knowledge_id="knowledge-uat",
                source_system="spreadsheet",
                source_record_id="uat.xlsx",
                source_version="3",
                locator="Sheet1!B4",
                content_fingerprint=sha256(text.encode()).hexdigest(),
            ),
            text=text,
        ),
    )


def test_extracts_grounded_procedure_and_resolves_prompt_aliases() -> None:
    model = FakeModel(
        {
            "title": "Create requisition",
            "steps": [{"instruction": "Submit eligible item", "evidence_ids": ["E1"]}],
            "exceptions": [
                {
                    "description": "Restricted item cannot be submitted",
                    "evidence_ids": ["E1"],
                }
            ],
            "gaps": [
                {
                    "description": "Navigation is not documented",
                    "kind": "missing_information",
                    "evidence_ids": ["E1"],
                }
            ],
        }
    )
    result = LangChainProcedureExtractor(model).extract(evidence())

    assert result.steps[0].evidence_refs[0].chunk_id == "uat-1"
    assert result.exceptions[0].evidence_refs[0].chunk_id == "uat-1"
    assert result.gaps[0].evidence_refs[0].chunk_id == "uat-1"
    assert result.gaps[0].kind is GapKind.MISSING_INFORMATION
    assert model.structured.messages is not None


def test_rejects_fabricated_citation() -> None:
    model = FakeModel(
        {
            "title": "Create requisition",
            "steps": [{"instruction": "Submit", "evidence_ids": ["E999"]}],
            "exceptions": [],
            "gaps": [],
        }
    )
    with pytest.raises(ValueError, match="unknown evidence"):
        LangChainProcedureExtractor(model).extract(evidence())


def test_requires_evidence() -> None:
    model = FakeModel({"title": "X", "steps": [], "exceptions": [], "gaps": []})
    with pytest.raises(ValueError, match="At least one"):
        LangChainProcedureExtractor(model).extract(())
