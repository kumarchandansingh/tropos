from tropos.application.ports.knowledge import (
    ClosureEvidenceEvaluator,
    KnowledgeCoverageEvaluator,
    KnowledgeDecisionStore,
    KnowledgeRetriever,
)
from tropos.domain.knowledge_action import (
    ClosureEvidenceStatus,
    KnowledgeCoverage,
    KnowledgeDecision,
    KnowledgeDecisionInput,
    decide_knowledge_action,
)
from tropos.domain.resolved_case import ResolvedCase


class EvaluateCaseClosure:
    """Coordinate evaluation of one resolved support case."""

    def __init__(
        self,
        closure_evidence_evaluator: ClosureEvidenceEvaluator,
        knowledge_retriever: KnowledgeRetriever,
        knowledge_coverage_evaluator: KnowledgeCoverageEvaluator,
        decision_store: KnowledgeDecisionStore,
        *,
        retrieval_limit: int = 5,
    ) -> None:
        if retrieval_limit < 1:
            raise ValueError("retrieval_limit must be positive")

        self._closure_evidence_evaluator = closure_evidence_evaluator
        self._knowledge_retriever = knowledge_retriever
        self._knowledge_coverage_evaluator = knowledge_coverage_evaluator
        self._decision_store = decision_store
        self._retrieval_limit = retrieval_limit

    def execute(self, resolved_case: ResolvedCase) -> KnowledgeDecision:
        closure_evidence = self._closure_evidence_evaluator.evaluate(resolved_case)
        knowledge_coverage: KnowledgeCoverage | None = None

        if closure_evidence is ClosureEvidenceStatus.SUFFICIENT:
            retrieved_knowledge = self._knowledge_retriever.retrieve(
                resolved_case,
                limit=self._retrieval_limit,
            )
            knowledge_coverage = self._knowledge_coverage_evaluator.evaluate(
                resolved_case,
                retrieved_knowledge,
            )

        decision = decide_knowledge_action(
            KnowledgeDecisionInput(
                case_id=resolved_case.case_id,
                closure_evidence=closure_evidence,
                knowledge_coverage=knowledge_coverage,
            )
        )

        self._decision_store.save(decision)

        return decision
