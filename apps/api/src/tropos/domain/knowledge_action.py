from dataclasses import dataclass
from enum import StrEnum


class ClosureEvidenceStatus(StrEnum):
    """Whether a resolved case contains usable closure evidence."""

    INSUFFICIENT = "INSUFFICIENT"
    SUFFICIENT = "SUFFICIENT"


class KnowledgeCoverage(StrEnum):
    """How well existing knowledge covers the resolved case."""

    NONE = "NONE"
    PARTIAL = "PARTIAL"
    SUFFICIENT = "SUFFICIENT"


class KnowledgeAction(StrEnum):
    """Permitted actions for the governed knowledge workflow."""

    REUSE = "REUSE"
    IMPROVE = "IMPROVE"
    CREATE = "CREATE"
    NO_ACTION = "NO_ACTION"


class DecisionReason(StrEnum):
    """Stable, auditable explanation for a knowledge action."""

    INSUFFICIENT_CLOSURE_EVIDENCE = "INSUFFICIENT_CLOSURE_EVIDENCE"
    NO_RELATED_KNOWLEDGE = "NO_RELATED_KNOWLEDGE"
    RELATED_KNOWLEDGE_INCOMPLETE = "RELATED_KNOWLEDGE_INCOMPLETE"
    RELATED_KNOWLEDGE_SUFFICIENT = "RELATED_KNOWLEDGE_SUFFICIENT"


@dataclass(frozen=True, slots=True)
class KnowledgeDecisionInput:
    """Validated facts required by the knowledge-action policy."""

    case_id: str
    closure_evidence: ClosureEvidenceStatus
    knowledge_coverage: KnowledgeCoverage | None = None

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be blank")

        if (
            self.closure_evidence is ClosureEvidenceStatus.SUFFICIENT
            and self.knowledge_coverage is None
        ):
            raise ValueError("knowledge_coverage is required when closure evidence is sufficient")

        if (
            self.closure_evidence is ClosureEvidenceStatus.INSUFFICIENT
            and self.knowledge_coverage is not None
        ):
            raise ValueError(
                "knowledge_coverage must not be supplied when closure evidence is insufficient"
            )


@dataclass(frozen=True, slots=True)
class KnowledgeDecision:
    """Auditable result produced by the domain policy."""

    case_id: str
    action: KnowledgeAction
    reason: DecisionReason


def decide_knowledge_action(
    decision_input: KnowledgeDecisionInput,
) -> KnowledgeDecision:
    """Choose an action from validated business facts."""

    if decision_input.closure_evidence is ClosureEvidenceStatus.INSUFFICIENT:
        return KnowledgeDecision(
            case_id=decision_input.case_id,
            action=KnowledgeAction.NO_ACTION,
            reason=DecisionReason.INSUFFICIENT_CLOSURE_EVIDENCE,
        )

    if decision_input.knowledge_coverage is KnowledgeCoverage.NONE:
        return KnowledgeDecision(
            case_id=decision_input.case_id,
            action=KnowledgeAction.CREATE,
            reason=DecisionReason.NO_RELATED_KNOWLEDGE,
        )

    if decision_input.knowledge_coverage is KnowledgeCoverage.PARTIAL:
        return KnowledgeDecision(
            case_id=decision_input.case_id,
            action=KnowledgeAction.IMPROVE,
            reason=DecisionReason.RELATED_KNOWLEDGE_INCOMPLETE,
        )

    if decision_input.knowledge_coverage is KnowledgeCoverage.SUFFICIENT:
        return KnowledgeDecision(
            case_id=decision_input.case_id,
            action=KnowledgeAction.REUSE,
            reason=DecisionReason.RELATED_KNOWLEDGE_SUFFICIENT,
        )

    raise AssertionError("validated decision input reached an impossible state")
