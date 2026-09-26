from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable
from uuid import uuid4

from tropos.core.application.ingestion.normalization import materialize_knowledge_document
from tropos.core.application.ingestion.parsing import KnowledgeParser
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.ingestion.run_state import (
    IngestionOutcome,
    IngestionResult,
    IngestionStage,
)
from tropos.core.application.ingestion.versioning import (
    VersionAction,
    resolve_canonical_version,
    state_from_candidate,
)
from tropos.core.application.ports.chunking import KnowledgeChunker
from tropos.core.application.ports.normalization import KnowledgeNormalizer
from tropos.core.application.ports.persistence import (
    IngestionRunStore,
    KnowledgeStateRepository,
    SourceCaptureStore,
)


@dataclass(frozen=True, slots=True)
class IngestKnowledgeCommand:
    """One immutable source capture to evaluate against canonical knowledge state."""

    knowledge_id: str
    raw_record: RawKnowledgeRecord
    source_uri: str | None = None
    source_updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.knowledge_id.strip():
            raise ValueError("knowledge_id must not be blank")
        if not isinstance(self.raw_record, RawKnowledgeRecord):
            raise TypeError("raw_record must be a RawKnowledgeRecord")
        if self.source_uri is not None and not self.source_uri.strip():
            raise ValueError("source_uri must not be blank when provided")
        if self.source_updated_at is not None and (
            self.source_updated_at.tzinfo is None
            or self.source_updated_at.utcoffset() is None
        ):
            raise ValueError("source_updated_at must include timezone information")


class IngestKnowledge:
    """Coordinate deterministic ingestion without owning worker implementation details."""

    def __init__(
        self,
        *,
        parser: KnowledgeParser,
        normalizer: KnowledgeNormalizer,
        chunker: KnowledgeChunker,
        source_captures: SourceCaptureStore,
        knowledge_repository: KnowledgeStateRepository,
        runs: IngestionRunStore,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._parser = parser
        self._normalizer = normalizer
        self._chunker = chunker
        self._source_captures = source_captures
        self._knowledge_repository = knowledge_repository
        self._runs = runs
        self._run_id_factory = run_id_factory or (lambda: uuid4().hex)

    def execute(self, command: IngestKnowledgeCommand) -> IngestionResult:
        fingerprint = command.raw_record.ingestion_fingerprint
        previous_result = self._runs.find_completed(
            knowledge_id=command.knowledge_id,
            ingestion_fingerprint=fingerprint,
        )
        if previous_result is not None:
            return replace(previous_result, replayed=True)

        self._source_captures.record(command.raw_record)

        run_id = self._run_id_factory().strip()
        if not run_id:
            raise ValueError("run_id_factory must return a non-blank value")

        self._runs.start(
            run_id=run_id,
            knowledge_id=command.knowledge_id,
            ingestion_fingerprint=fingerprint,
        )

        stage = IngestionStage.RECEIVED
        try:
            stage = IngestionStage.PARSING
            self._runs.set_stage(run_id, stage)
            extracted = self._parser.parse(
                command.raw_record,
                source_uri=command.source_uri,
                source_updated_at=command.source_updated_at,
            )

            stage = IngestionStage.NORMALIZING
            self._runs.set_stage(run_id, stage)
            normalized = self._normalizer.normalize(extracted)

            stage = IngestionStage.DECIDING
            self._runs.set_stage(run_id, stage)
            previous_state = self._knowledge_repository.get_current_state(command.knowledge_id)
            decision = resolve_canonical_version(
                previous=previous_state,
                candidate=normalized,
            )
            candidate_state = state_from_candidate(normalized)

            governance_refreshed = False
            expected_for_version = previous_state

            if decision.requires_governance_refresh:
                if previous_state is None:
                    raise RuntimeError("governance refresh requires persisted prior state")
                stage = IngestionStage.PERSISTING
                self._runs.set_stage(run_id, stage)
                expected_for_version = self._knowledge_repository.refresh_governance(
                    knowledge_id=command.knowledge_id,
                    access_policy=command.raw_record.access_policy,
                    expected_state=previous_state,
                )
                governance_refreshed = True

            chunks_written = 0
            if decision.action is VersionAction.CREATE_VERSION:
                document = materialize_knowledge_document(
                    knowledge_id=command.knowledge_id,
                    normalized=normalized,
                )
                stage = IngestionStage.CHUNKING
                self._runs.set_stage(run_id, stage)
                chunks = self._chunker.chunk(document)

                stage = IngestionStage.PERSISTING
                self._runs.set_stage(run_id, stage)
                self._knowledge_repository.create_version(
                    document=document,
                    chunks=chunks,
                    state=candidate_state,
                    expected_previous=expected_for_version,
                )
                chunks_written = len(chunks)
                outcome = IngestionOutcome.VERSION_CREATED
            elif decision.action is VersionAction.NO_CONTENT_VERSION:
                outcome = IngestionOutcome.NO_CHANGE
            elif decision.action is VersionAction.REFRESH_GOVERNANCE:
                outcome = IngestionOutcome.GOVERNANCE_REFRESHED
            else:
                outcome = IngestionOutcome.REBASELINE_REQUIRED

            result = IngestionResult(
                run_id=run_id,
                knowledge_id=command.knowledge_id,
                ingestion_fingerprint=fingerprint,
                outcome=outcome,
                action=decision.action,
                reason=decision.reason,
                canonical_content_fingerprint=normalized.content_fingerprint,
                chunks_written=chunks_written,
                governance_refreshed=governance_refreshed,
            )
            self._runs.complete(result)
            return result
        except Exception as exc:
            self._runs.fail(
                run_id=run_id,
                stage=stage,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise
