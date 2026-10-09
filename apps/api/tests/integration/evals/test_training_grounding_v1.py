import json
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from tropos.capabilities.training.langchain_extractor import LangChainProcedureExtractor
from tropos.capabilities.training.procedure import EvidenceExcerpt
from tropos.core.domain.evidence import EvidenceRef
from tropos.evals.training import (
    ExpectedClaim,
    ExpectedStep,
    TrainingEvalCase,
    evaluate_procedure,
)

DATASET = Path(__file__).parents[3] / "evals/training/procedure_grounding_v1.json"


class FakeStructuredModel:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def invoke(self, messages: Any) -> dict[str, Any]:
        return self.response


class FakeModel:
    def __init__(self, response: dict[str, Any]) -> None:
        self.structured = FakeStructuredModel(response)

    def with_structured_output(self, schema: Any) -> FakeStructuredModel:
        assert schema is not None
        return self.structured


def _load() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(DATASET.read_text(encoding="utf-8")))


def _excerpt(raw: dict[str, Any]) -> EvidenceExcerpt:
    text = cast(str, raw["text"])
    locator = cast(str, raw["locator"])
    source_id = cast(str, raw["source_id"])
    return EvidenceExcerpt(
        reference=EvidenceRef(
            chunk_id=source_id,
            knowledge_id=source_id,
            source_system=locator.split(":", 1)[0],
            source_record_id=source_id,
            source_version="synthetic-v1",
            locator=locator,
            content_fingerprint=sha256(text.encode()).hexdigest(),
        ),
        text=text,
    )


def _expected_claim(raw: dict[str, Any]) -> ExpectedClaim:
    return ExpectedClaim(
        contains=raw["contains"],
        evidence_chunk_ids=tuple(raw["evidence_chunk_ids"]),
    )


def _case(raw: dict[str, Any]) -> TrainingEvalCase:
    return TrainingEvalCase(
        case_id=raw["case_id"],
        expected_steps=tuple(
            ExpectedStep(step["contains"], tuple(step["evidence_chunk_ids"]))
            for step in raw["expected_steps"]
        ),
        forbidden_step_terms=tuple(raw["forbidden_step_terms"]),
        expected_exceptions=tuple(
            _expected_claim(item) for item in raw["expected_exceptions"]
        ),
        expected_gaps=tuple(_expected_claim(item) for item in raw["expected_gaps"]),
    )


def test_grounding_dataset_covers_four_failure_archetypes() -> None:
    dataset = _load()
    assert dataset["dataset_id"] == "tropos-training-procedure-grounding-v1"
    assert [case["case_id"] for case in dataset["cases"]] == [
        "happy-path-requisition",
        "negative-uat-is-exception",
        "missing-navigation-becomes-gap",
        "conflicting-evidence-becomes-gap",
    ]


def test_evaluator_accepts_grounded_candidate() -> None:
    raw = _load()["cases"][1]
    evidence = tuple(_excerpt(item) for item in raw["evidence"])
    model = FakeModel(
        {
            "title": "Submit requisition",
            "steps": [{"instruction": "Submit the requisition", "evidence_ids": ["E1"]}],
            "exceptions": [
                {
                    "description": "Submission is blocked when the supplier is inactive.",
                    "evidence_ids": ["E2"],
                }
            ],
            "gaps": [],
        }
    )
    draft = LangChainProcedureExtractor(model).extract(evidence)
    result = evaluate_procedure(_case(raw), draft)
    assert result.passed is True
    assert result.step_coverage == 1.0
    assert result.citation_alignment == 1.0
    assert result.exception_separation is True


def test_evaluator_rejects_negative_uat_promoted_to_normal_step() -> None:
    raw = _load()["cases"][1]
    evidence = tuple(_excerpt(item) for item in raw["evidence"])
    model = FakeModel(
        {
            "title": "Submit requisition",
            "steps": [
                {"instruction": "Submit the requisition", "evidence_ids": ["E1"]},
                {"instruction": "Use an inactive supplier", "evidence_ids": ["E2"]},
            ],
            "exceptions": [
                {
                    "description": "Submission is blocked when the supplier is inactive.",
                    "evidence_ids": ["E2"],
                }
            ],
            "gaps": [],
        }
    )
    draft = LangChainProcedureExtractor(model).extract(evidence)
    result = evaluate_procedure(_case(raw), draft)
    assert result.passed is False
    assert result.exception_separation is False


def test_evaluator_rejects_wrong_citation_even_when_step_text_is_correct() -> None:
    raw = _load()["cases"][0]
    evidence = tuple(_excerpt(item) for item in raw["evidence"])
    model = FakeModel(
        {
            "title": "Create requisition",
            "steps": [
                {"instruction": "Enter supplier and item details", "evidence_ids": ["E2"]},
                {"instruction": "Submit the requisition", "evidence_ids": ["E2"]},
            ],
            "exceptions": [],
            "gaps": [],
        }
    )
    draft = LangChainProcedureExtractor(model).extract(evidence)
    result = evaluate_procedure(_case(raw), draft)
    assert result.step_coverage == 1.0
    assert result.citation_alignment == 0.5
    assert result.passed is False
