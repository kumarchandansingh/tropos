from typing import Protocol

from tropos.domain.knowledge import KnowledgeDocument
from tropos.domain.knowledge_chunk import KnowledgeChunk


class KnowledgeChunker(Protocol):
    """Create validated chunks without exposing an implementation framework."""

    def chunk(self, document: KnowledgeDocument) -> tuple[KnowledgeChunk, ...]: ...
