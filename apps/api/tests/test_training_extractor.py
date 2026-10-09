"""Deterministic contract tests; no model credentials or network calls required."""

from typing import Any

import pytest

from tropos.capabilities.training.langchain_extractor import LangChainProcedureExtractor
from tropos.capabilities.training.procedure import EvidenceExcerpt


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
    return (EvidenceExcerpt("uat-1", "Sheet1!B4", "Submit an eligible item"),)


def test_extracts_cited_procedure() -> None:
    model = FakeModel({
        "title": "Create requisition",
        "steps": [{"instruction": "Submit eligible item", "evidence_ids": ["1"]}],
        "exceptions": ["Restricted item cannot be submitted"],
        "gaps": ["Navigation is not documented"],
    })
    result = LangChainProcedureExtractor(model).extract(evidence())
    assert result.steps[0].evidence_ids == ("1",)
    assert result.gaps == ("Navigation is not documented",)
    assert model.structured.messages is not None


def test_rejects_fabricated_citation() -> None:
    model = FakeModel({
        "title": "Create requisition",
        "steps": [{"instruction": "Submit", "evidence_ids": ["999"]}],
        "exceptions": [],
        "gaps": [],
    })
    with pytest.raises(ValueError, match="unknown evidence"):
        LangChainProcedureExtractor(model).extract(evidence())


def test_requires_evidence() -> None:
    model = FakeModel({"title": "X", "steps": [], "exceptions": [], "gaps": []})
    with pytest.raises(ValueError, match="At least one"):
        LangChainProcedureExtractor(model).extract(())
