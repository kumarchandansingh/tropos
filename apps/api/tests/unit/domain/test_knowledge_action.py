import pytest

from tropos.domain.knowledge_action import (
    ClosureEvidenceStatus,
    DecisionReason,
    KnowledgeAction,
    KnowledgeCoverage,
    KnowledgeDecisionInput,
    decide_knowledge_action,
)


def test_insufficient_evidence_produces_no_action() -> None:
    decision_input = KnowledgeDecisionInput(
        case_id="CASE-001",
        closure_evidence=ClosureEvidenceStatus.INSUFFICIENT,
    )

    decision = decide_knowledge_action(decision_input)

    assert decision.action is KnowledgeAction.NO_ACTION
    assert decision.reason is DecisionReason.INSUFFICIENT_CLOSURE_EVIDENCE


def test_no_related_knowledge_produces_create() -> None:
    decision_input = KnowledgeDecisionInput(
        case_id="CASE-002",
        closure_evidence=ClosureEvidenceStatus.SUFFICIENT,
        knowledge_coverage=KnowledgeCoverage.NONE,
    )

    decision = decide_knowledge_action(decision_input)

    assert decision.action is KnowledgeAction.CREATE
    assert decision.reason is DecisionReason.NO_RELATED_KNOWLEDGE


def test_partial_knowledge_produces_improve() -> None:
    decision_input = KnowledgeDecisionInput(
        case_id="CASE-003",
        closure_evidence=ClosureEvidenceStatus.SUFFICIENT,
        knowledge_coverage=KnowledgeCoverage.PARTIAL,
    )

    decision = decide_knowledge_action(decision_input)

    assert decision.action is KnowledgeAction.IMPROVE
    assert decision.reason is DecisionReason.RELATED_KNOWLEDGE_INCOMPLETE


def test_sufficient_knowledge_produces_reuse() -> None:
    decision_input = KnowledgeDecisionInput(
        case_id="CASE-004",
        closure_evidence=ClosureEvidenceStatus.SUFFICIENT,
        knowledge_coverage=KnowledgeCoverage.SUFFICIENT,
    )

    decision = decide_knowledge_action(decision_input)

    assert decision.action is KnowledgeAction.REUSE
    assert decision.reason is DecisionReason.RELATED_KNOWLEDGE_SUFFICIENT


def test_blank_case_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="case_id must not be blank"):
        KnowledgeDecisionInput(
            case_id=" ",
            closure_evidence=ClosureEvidenceStatus.INSUFFICIENT,
        )


def test_coverage_is_required_for_sufficient_evidence() -> None:
    with pytest.raises(ValueError, match="knowledge_coverage is required"):
        KnowledgeDecisionInput(
            case_id="CASE-005",
            closure_evidence=ClosureEvidenceStatus.SUFFICIENT,
        )


def test_coverage_is_rejected_for_insufficient_evidence() -> None:
    with pytest.raises(ValueError, match="knowledge_coverage must not be supplied"):
        KnowledgeDecisionInput(
            case_id="CASE-006",
            closure_evidence=ClosureEvidenceStatus.INSUFFICIENT,
            knowledge_coverage=KnowledgeCoverage.PARTIAL,
        )
