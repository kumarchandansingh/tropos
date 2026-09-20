from typing import Protocol

from tropos.domain.knowledge import KnowledgeDocument
from tropos.domain.knowledge_chunk import KnowledgeChunk


class KnowledgeCorpusStore(Protocol):
    """Persist and reload the current governed knowledge corpus."""

    def save(
        self,
        document: KnowledgeDocument,
        chunks: tuple[KnowledgeChunk, ...],
    ) -> None: ...

    def get_document(self, knowledge_id: str) -> KnowledgeDocument | None: ...

    def get_chunks(self, knowledge_id: str) -> tuple[KnowledgeChunk, ...]: ...
