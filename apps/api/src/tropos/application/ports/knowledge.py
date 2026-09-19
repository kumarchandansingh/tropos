from typing import Protocol

from tropos.domain.knowledge_action import (
    ClosureEvidenceStatus,
    KnowledgeCoverage,
    KnowledgeDecision,
)
from tropos.domain.resolved_case import ResolvedCase


class ClosureEvidenceEvaluator(Protocol):
    """Assess whether a resolved case contains usable closure evidence."""

    def evaluate(self, resolved_case: ResolvedCase) -> ClosureEvidenceStatus: ...


class KnowledgeCoverageEvaluator(Protocol):
    """Assess how well existing knowledge covers a resolved case."""

    def evaluate(self, resolved_case: ResolvedCase) -> KnowledgeCoverage: ...


class KnowledgeDecisionStore(Protocol):
    """Persist an auditable knowledge decision."""

    def save(self, decision: KnowledgeDecision) -> None: ...
