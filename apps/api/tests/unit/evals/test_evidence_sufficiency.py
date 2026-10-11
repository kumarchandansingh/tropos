from datetime import UTC, datetime
from pathlib import Path

import pytest

from tropos.evals.contracts import EvalApproval, EvalSplit
from tropos.evals.evidence_sufficiency import (
    EvidenceSnippet,
    EvidenceSourceReference,
    EvidenceSourceRole,
    EvidenceSufficiencyBenchmark,
    EvidenceSufficiencyCase,
    EvidenceSufficiencyLabel,
    EvidenceSufficiencyReason,
    HumanSufficiencyReview,
    load_evidence_sufficiency_benchmark,
)


def _source() -> EvidenceSourceReference:
    return EvidenceSourceReference(
        source_id="SRC-1",
        role=EvidenceSourceRole.PRIMARY,
        title="Public source",
        url="https://example.com/source",
    )


def _review(
    *,
    reviewer: str = "reviewer-1",
    label: EvidenceSufficiencyLabel = EvidenceSufficiencyLabel.SUFFICIENT,
    reason: EvidenceSufficiencyReason = EvidenceSufficiencyReason.NONE,
    required_facts: tuple[str, ...] = ("fact one",),
    missing_facts: tuple[str, ...] = (),
    would_answer: bool = True,
) -> HumanSufficiencyReview:
    return HumanSufficiencyReview(
        reviewer=reviewer,
        reviewed_at=datetime(2026, 10, 11, tzinfo=UTC),
        label=label,
        reason=reason,
        required_facts=required_facts,
        missing_facts=missing_facts,
        confidence=4,
        would_answer=would_answer,
    )


def _case(
    *,
    approval: EvalApproval = EvalApproval.CANDIDATE,
    reviews: tuple[HumanSufficiencyReview, ...] = (),
    adjudication: HumanSufficiencyReview | None = None,
) -> EvidenceSufficiencyCase:
    return EvidenceSufficiencyCase(
        case_id="case-1",
        evidence_set_id="evidence-set-1",
        split=EvalSplit.DEVELOPMENT,
        approval=approval,
        query="Can the evidence support the answer?",
        evidence=(
            EvidenceSnippet(
                evidence_id="E1",
                text="The first required fact is present.",
            ),
        ),
        pattern_ids=("PATTERN-1",),
        source_references=(_source(),),
        reviews=reviews,
        adjudication=adjudication,
        tags=("fixture",),
    )


def test_candidate_case_cannot_be_projected_as_a_golden() -> None:
    case = _case()

    with pytest.raises(ValueError, match="approved human-adjudicated"):
        case.to_eval_case()


def test_approved_case_requires_human_review_and_adjudication() -> None:
    with pytest.raises(ValueError, match="human review"):
        _case(
            approval=EvalApproval.APPROVED,
            reviews=(),
            adjudication=_review(),
        )

    with pytest.raises(ValueError, match="human adjudication"):
        _case(
            approval=EvalApproval.APPROVED,
            reviews=(_review(),),
            adjudication=None,
        )


def test_sufficient_review_requires_none_reason_and_no_missing_facts() -> None:
    with pytest.raises(ValueError, match="reason NONE"):
        _review(reason=EvidenceSufficiencyReason.WEAK_SUPPORT)

    with pytest.raises(ValueError, match="must not declare missing facts"):
        _review(missing_facts=("missing item",))


def test_insufficient_review_requires_reason_and_abstention() -> None:
    with pytest.raises(ValueError, match="requires a reason"):
        _review(
            label=EvidenceSufficiencyLabel.INSUFFICIENT,
            reason=EvidenceSufficiencyReason.NONE,
            would_answer=False,
        )

    with pytest.raises(ValueError, match="must abstain"):
        _review(
            label=EvidenceSufficiencyLabel.INSUFFICIENT,
            reason=EvidenceSufficiencyReason.MISSING_CRITICAL_FACT,
            missing_facts=("policy layer",),
            would_answer=True,
        )


def test_approved_case_projects_human_adjudication_to_generic_eval_case() -> None:
    review = _review(reviewer="reviewer-1")
    adjudication = _review(reviewer="lead-reviewer")
    case = _case(
        approval=EvalApproval.APPROVED,
        reviews=(review,),
        adjudication=adjudication,
    )

    projected = case.to_eval_case()

    assert projected.approval is EvalApproval.APPROVED
    assert projected.inputs["query"] == case.query
    assert projected.expected["label"] == "SUFFICIENT"
    assert projected.expected["reason"] == "NONE"
    assert projected.expected["should_abstain"] is False
    assert projected.expected["human_adjudicator"] == "lead-reviewer"
    assert projected.expected["human_review_count"] == 1


def test_approved_dataset_excludes_candidate_cases() -> None:
    review = _review()
    approved = EvidenceSufficiencyCase(
        case_id="approved-1",
        evidence_set_id="approved-set-1",
        split=EvalSplit.DEVELOPMENT,
        approval=EvalApproval.APPROVED,
        query="Approved query",
        evidence=(EvidenceSnippet("E1", "Enough evidence."),),
        pattern_ids=("PATTERN-1",),
        source_references=(_source(),),
        reviews=(review,),
        adjudication=review,
    )
    benchmark = EvidenceSufficiencyBenchmark(
        dataset_id="sufficiency",
        version="v1",
        notes="fixture",
        cases=(_case(), approved),
    )

    dataset = benchmark.approved_dataset(EvalSplit.DEVELOPMENT)

    assert len(dataset.cases) == 1
    assert dataset.cases[0].case_id == "approved-1"


def test_candidate_benchmark_loads_without_promoting_ai_preparation_to_gold() -> None:
    path = (
        Path(__file__).parents[3] / "evals" / "resolve" / "evidence_sufficiency_candidates_v1.json"
    )

    benchmark = load_evidence_sufficiency_benchmark(path)

    assert len(benchmark.cases) == 16
    assert benchmark.candidate_count == 16
    assert benchmark.approved_count == 0
    assert {case.approval for case in benchmark.cases} == {EvalApproval.CANDIDATE}
    assert all(not case.reviews for case in benchmark.cases)
    assert all(case.adjudication is None for case in benchmark.cases)

    with pytest.raises(ValueError, match="no human-adjudicated approved"):
        benchmark.approved_dataset(EvalSplit.DEVELOPMENT)


def test_duplicate_evidence_set_identity_is_rejected() -> None:
    first = _case()
    second = EvidenceSufficiencyCase(
        case_id="case-2",
        evidence_set_id=first.evidence_set_id,
        split=EvalSplit.HOLDOUT,
        approval=EvalApproval.CANDIDATE,
        query="Another query",
        evidence=(EvidenceSnippet("E2", "Another evidence set."),),
        pattern_ids=("PATTERN-2",),
        source_references=(_source(),),
    )

    with pytest.raises(ValueError, match="evidence set IDs must be unique"):
        EvidenceSufficiencyBenchmark(
            dataset_id="sufficiency",
            version="v1",
            notes="fixture",
            cases=(first, second),
        )
