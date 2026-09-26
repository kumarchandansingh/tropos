from dataclasses import dataclass
from enum import StrEnum

from tropos.core.application.ingestion.versioning import VersionAction, VersionReason


class IngestionStage(StrEnum):
    """Durable stage marker for one synchronous ingestion attempt."""

    RECEIVED = "RECEIVED"
    PARSING = "PARSING"
    NORMALIZING = "NORMALIZING"
    DECIDING = "DECIDING"
    CHUNKING = "CHUNKING"
    PERSISTING = "PERSISTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class IngestionOutcome(StrEnum):
    """Externally meaningful result of a completed ingestion attempt."""

    VERSION_CREATED = "VERSION_CREATED"
    NO_CHANGE = "NO_CHANGE"
    GOVERNANCE_REFRESHED = "GOVERNANCE_REFRESHED"
    REBASELINE_REQUIRED = "REBASELINE_REQUIRED"


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Auditable result returned by the ingestion orchestrator."""

    run_id: str
    knowledge_id: str
    ingestion_fingerprint: str
    outcome: IngestionOutcome
    action: VersionAction
    reason: VersionReason
    canonical_content_fingerprint: str
    chunks_written: int
    governance_refreshed: bool
    replayed: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be blank")
        if not self.knowledge_id.strip():
            raise ValueError("knowledge_id must not be blank")
        if len(self.ingestion_fingerprint) != 64:
            raise ValueError("ingestion_fingerprint must be a SHA-256 digest")
        if len(self.canonical_content_fingerprint) != 64:
            raise ValueError("canonical_content_fingerprint must be a SHA-256 digest")
        if self.chunks_written < 0:
            raise ValueError("chunks_written must not be negative")
