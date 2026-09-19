from dataclasses import dataclass

from tropos.domain.knowledge_action import ClosureEvidenceStatus
from tropos.domain.resolved_case import ResolvedCase


@dataclass(frozen=True, slots=True)
class ClosureEvidenceRules:
    """Configurable deterministic requirements for closure evidence."""

    minimum_problem_characters: int = 20
    minimum_resolution_characters: int = 20

    def __post_init__(self) -> None:
        if self.minimum_problem_characters < 1:
            raise ValueError("minimum_problem_characters must be positive")

        if self.minimum_resolution_characters < 1:
            raise ValueError("minimum_resolution_characters must be positive")


class RuleBasedClosureEvidenceEvaluator:
    """Evaluate closure evidence without external systems or AI."""

    def __init__(self, rules: ClosureEvidenceRules | None = None) -> None:
        self._rules = rules or ClosureEvidenceRules()

    def evaluate(self, resolved_case: ResolvedCase) -> ClosureEvidenceStatus:
        normalized_problem = " ".join(resolved_case.problem_summary.split())
        normalized_resolution = " ".join(resolved_case.resolution_summary.split())

        problem_is_usable = len(normalized_problem) >= self._rules.minimum_problem_characters
        resolution_is_usable = (
            len(normalized_resolution) >= self._rules.minimum_resolution_characters
        )

        if problem_is_usable and resolution_is_usable:
            return ClosureEvidenceStatus.SUFFICIENT

        return ClosureEvidenceStatus.INSUFFICIENT
