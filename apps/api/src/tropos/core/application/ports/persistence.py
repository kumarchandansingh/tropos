from typing import Protocol

from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.ingestion.run_state import IngestionResult, IngestionStage
from tropos.core.application.ingestion.versioning import CanonicalKnowledgeState
from tropos.core.domain.access import AccessPolicy
from tropos.core.domain.knowledge import KnowledgeDocument
from tropos.core.domain.knowledge_chunk import KnowledgeChunk


class ConcurrentKnowledgeUpdateError(RuntimeError):
    """Raised when persisted canonical state changed after it was read."""


class IngestionAlreadyInProgressError(RuntimeError):
    """Raised when the same immutable source capture is already being processed."""


class SourceCaptureStore(Protocol):
    """Persist exact source evidence before canonical processing mutates nothing."""

    def record(self, raw_record: RawKnowledgeRecord) -> None: ...


class KnowledgeStateRepository(Protocol):
    """Persist canonical state, versions, chunks, and retrieval governance atomically."""

    def get_current_state(self, knowledge_id: str) -> CanonicalKnowledgeState | None: ...

    def refresh_governance(
        self,
        *,
        knowledge_id: str,
        access_policy: AccessPolicy,
        expected_state: CanonicalKnowledgeState,
    ) -> CanonicalKnowledgeState: ...

    def create_version(
        self,
        *,
        document: KnowledgeDocument,
        chunks: tuple[KnowledgeChunk, ...],
        state: CanonicalKnowledgeState,
        expected_previous: CanonicalKnowledgeState | None,
    ) -> None: ...


class IngestionRunStore(Protocol):
    """Persist workflow state and completed outcomes for replay and recovery."""

    def find_completed(
        self,
        *,
        knowledge_id: str,
        ingestion_fingerprint: str,
    ) -> IngestionResult | None: ...

    def start(
        self,
        *,
        run_id: str,
        knowledge_id: str,
        ingestion_fingerprint: str,
    ) -> None: ...

    def set_stage(self, run_id: str, stage: IngestionStage) -> None: ...

    def complete(self, result: IngestionResult) -> None: ...

    def fail(
        self,
        *,
        run_id: str,
        stage: IngestionStage,
        error_type: str,
        error_message: str,
    ) -> None: ...
