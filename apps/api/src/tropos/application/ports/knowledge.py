from typing import Protocol

from tropos.domain.knowledge import RetrievedKnowledge
from tropos.domain.knowledge_action import (
    ClosureEvidenceStatus,
    KnowledgeCoverage,
    KnowledgeDecision,
)
from tropos.domain.resolved_case import ResolvedCase


class ClosureEvidenceEvaluator(Protocol):
    """Assess whether a resolved case contains usable closure evidence."""

    def evaluate(self, resolved_case: ResolvedCase) -> ClosureEvidenceStatus: ...


class KnowledgeRetriever(Protocol):
    """Retrieve ranked knowledge candidates for a resolved case."""

    def retrieve(
        self,
        resolved_case: ResolvedCase,
        *,
        limit: int,
    ) -> tuple[RetrievedKnowledge, ...]: ...


class KnowledgeCoverageEvaluator(Protocol):
    """Assess how well retrieved knowledge covers a resolved case."""

    def evaluate(
        self,
        resolved_case: ResolvedCase,
        retrieved_knowledge: tuple[RetrievedKnowledge, ...],
    ) -> KnowledgeCoverage: ...


class KnowledgeDecisionStore(Protocol):
    """Persist an auditable knowledge decision."""

    def save(self, decision: KnowledgeDecision) -> None: ...
