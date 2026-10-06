from dataclasses import dataclass
from datetime import datetime

from tropos.core.application.ingestion.versioning import (
    CanonicalKnowledgeState,
    KnowledgeLifecycleStatus,
)
from tropos.core.application.ports.persistence import KnowledgeStateRepository


class KnowledgeSourceIdentityMismatchError(RuntimeError):
    """Raised when a lifecycle event targets a different source object."""


@dataclass(frozen=True, slots=True)
class RetireKnowledgeCommand:
    """Authoritative source deletion/tombstone for one Tropos knowledge identity."""

    knowledge_id: str
    source_system: str
    source_record_id: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.knowledge_id.strip():
            raise ValueError("knowledge_id must not be blank")
        if not self.source_system.strip():
            raise ValueError("source_system must not be blank")
        if not self.source_record_id.strip():
            raise ValueError("source_record_id must not be blank")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include timezone information")


class RetireKnowledge:
    """Mark current knowledge non-retrievable without deleting audit history."""

    def __init__(self, repository: KnowledgeStateRepository) -> None:
        self._repository = repository

    def execute(self, command: RetireKnowledgeCommand) -> CanonicalKnowledgeState:
        state = self._repository.retire(
            knowledge_id=command.knowledge_id,
            source_system=command.source_system,
            source_record_id=command.source_record_id,
            observed_at=command.observed_at.isoformat(),
        )
        if state.lifecycle_status is not KnowledgeLifecycleStatus.DELETED:
            raise RuntimeError("retirement did not produce DELETED lifecycle state")
        return state
