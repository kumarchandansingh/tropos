from typing import Protocol

from tropos.core.domain.knowledge import KnowledgeDocument
from tropos.core.domain.knowledge_chunk import KnowledgeChunk


class KnowledgeChunker(Protocol):
    """Create validated chunks without exposing an implementation framework."""

    def chunk(self, document: KnowledgeDocument) -> tuple[KnowledgeChunk, ...]: ...
