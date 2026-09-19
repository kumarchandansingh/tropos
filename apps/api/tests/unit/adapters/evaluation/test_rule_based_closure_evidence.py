from datetime import UTC, datetime

import pytest

from tropos.adapters.evaluation.rule_based_closure_evidence import (
    ClosureEvidenceRules,
    RuleBasedClosureEvidenceEvaluator,
)
from tropos.domain.knowledge_action import ClosureEvidenceStatus
from tropos.domain.resolved_case import ResolvedCase


def build_resolved_case(
    *,
    problem_summary: str = "Customer could not authenticate after resetting the password.",
    resolution_summary: str = "Regenerated the credential and confirmed successful authentication.",
) -> ResolvedCase:
    return ResolvedCase(
        case_id="CASE-001",
        source_system="test-source",
        source_record_id="SOURCE-001",
        title="Authentication failure",
        problem_summary=problem_summary,
        resolution_summary=resolution_summary,
        resolved_at=datetime(2026, 9, 19, tzinfo=UTC),
    )


def test_complete_evidence_is_sufficient() -> None:
    evaluator = RuleBasedClosureEvidenceEvaluator()

    result = evaluator.evaluate(build_resolved_case())

    assert result is ClosureEvidenceStatus.SUFFICIENT


def test_short_problem_is_insufficient() -> None:
    evaluator = RuleBasedClosureEvidenceEvaluator()

    result = evaluator.evaluate(build_resolved_case(problem_summary="Login failed."))

    assert result is ClosureEvidenceStatus.INSUFFICIENT


def test_whitespace_only_resolution_is_insufficient() -> None:
    evaluator = RuleBasedClosureEvidenceEvaluator()

    result = evaluator.evaluate(build_resolved_case(resolution_summary="     "))

    assert result is ClosureEvidenceStatus.INSUFFICIENT


def test_non_positive_rule_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="minimum_problem_characters must be positive",
    ):
        ClosureEvidenceRules(minimum_problem_characters=0)
