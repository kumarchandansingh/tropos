from dataclasses import dataclass, field
from datetime import UTC, datetime

from tropos.application.evaluate_case_closure import EvaluateCaseClosure
from tropos.domain.knowledge_action import (
    ClosureEvidenceStatus,
    KnowledgeAction,
    KnowledgeCoverage,
    KnowledgeDecision,
)
from tropos.domain.resolved_case import ResolvedCase


@dataclass
class StubClosureEvidenceEvaluator:
    result: ClosureEvidenceStatus

    def evaluate(self, resolved_case: ResolvedCase) -> ClosureEvidenceStatus:
        return self.result


@dataclass
class StubKnowledgeCoverageEvaluator:
    result: KnowledgeCoverage
    calls: int = 0

    def evaluate(self, resolved_case: ResolvedCase) -> KnowledgeCoverage:
        self.calls += 1
        return self.result


@dataclass
class InMemoryKnowledgeDecisionStore:
    saved_decisions: list[KnowledgeDecision] = field(default_factory=list)

    def save(self, decision: KnowledgeDecision) -> None:
        self.saved_decisions.append(decision)


def build_resolved_case() -> ResolvedCase:
    return ResolvedCase(
        case_id="CASE-001",
        source_system="test-source",
        source_record_id="SOURCE-001",
        title="Login failure",
        problem_summary="Customer could not authenticate.",
        resolution_summary="Reset the expired authentication credential.",
        resolved_at=datetime(2026, 9, 19, tzinfo=UTC),
    )


def test_insufficient_evidence_skips_knowledge_evaluation() -> None:
    evidence_evaluator = StubClosureEvidenceEvaluator(ClosureEvidenceStatus.INSUFFICIENT)
    knowledge_evaluator = StubKnowledgeCoverageEvaluator(KnowledgeCoverage.SUFFICIENT)
    decision_store = InMemoryKnowledgeDecisionStore()
    use_case = EvaluateCaseClosure(
        evidence_evaluator,
        knowledge_evaluator,
        decision_store,
    )

    decision = use_case.execute(build_resolved_case())

    assert decision.action is KnowledgeAction.NO_ACTION
    assert knowledge_evaluator.calls == 0
    assert decision_store.saved_decisions == [decision]


def test_sufficient_evidence_triggers_knowledge_evaluation() -> None:
    evidence_evaluator = StubClosureEvidenceEvaluator(ClosureEvidenceStatus.SUFFICIENT)
    knowledge_evaluator = StubKnowledgeCoverageEvaluator(KnowledgeCoverage.NONE)
    decision_store = InMemoryKnowledgeDecisionStore()
    use_case = EvaluateCaseClosure(
        evidence_evaluator,
        knowledge_evaluator,
        decision_store,
    )

    decision = use_case.execute(build_resolved_case())

    assert decision.action is KnowledgeAction.CREATE
    assert knowledge_evaluator.calls == 1
    assert decision_store.saved_decisions == [decision]
