from typing import Protocol

from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievedKnowledgeChunk,
)


class KnowledgeChunkRetriever(Protocol):
    """Retrieve authorized, ranked evidence chunks for a search request."""

    @property
    def strategy_version(self) -> str:
        """Stable identifier for the retrieval behavior used by this adapter."""
        ...

    def search(self, request: KnowledgeSearchRequest) -> tuple[RetrievedKnowledgeChunk, ...]:
        """Return ranked evidence without exposing unauthorized chunks."""
        ...
