from dataclasses import dataclass

from tropos.core.application.ingestion.ingest_knowledge import (
    IngestKnowledge,
    IngestKnowledgeCommand,
)
from tropos.core.application.ingestion.run_state import IngestionResult
from tropos.core.application.ports.sources import (
    KnowledgeSourceConnector,
    SourceIdentityMismatchError,
)


@dataclass(frozen=True, slots=True)
class IngestFromSourceCommand:
    """Select one source-native record and map it to one Tropos knowledge identity."""

    knowledge_id: str
    source_record_id: str

    def __post_init__(self) -> None:
        if not self.knowledge_id.strip():
            raise ValueError("knowledge_id must not be blank")
        if not self.source_record_id.strip():
            raise ValueError("source_record_id must not be blank")


class IngestFromSource:
    """Bridge a replaceable source connector into the stable ingestion workflow."""

    def __init__(
        self,
        *,
        connector: KnowledgeSourceConnector,
        ingestion: IngestKnowledge,
    ) -> None:
        self._connector = connector
        self._ingestion = ingestion

    def execute(self, command: IngestFromSourceCommand) -> IngestionResult:
        namespace = self._connector.source_namespace.strip()
        if not namespace:
            raise ValueError("connector source_namespace must not be blank")

        capture = self._connector.capture(command.source_record_id)
        if capture.raw_record.source_system != namespace:
            raise SourceIdentityMismatchError(
                "connector capture source_system must match connector source_namespace"
            )

        return self._ingestion.execute(
            IngestKnowledgeCommand(
                knowledge_id=command.knowledge_id,
                raw_record=capture.raw_record,
                source_uri=capture.source_uri,
                source_updated_at=capture.source_updated_at,
            )
        )
