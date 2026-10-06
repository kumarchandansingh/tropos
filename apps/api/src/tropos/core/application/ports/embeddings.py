from typing import Protocol

from tropos.core.application.embeddings.models import (
    EmbeddedKnowledgeChunk,
    EmbeddingVector,
    KnowledgeEmbedding,
    SimilarityMetric,
)
from tropos.core.application.retrieval.models import RetrievalAccessContext
from tropos.core.domain.knowledge_chunk import KnowledgeChunk


class EmbeddingProvider(Protocol):
    """Produce compatible query and document vectors behind a replaceable provider."""

    @property
    def strategy_version(self) -> str: ...

    @property
    def model_identifier(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    @property
    def similarity_metric(self) -> SimilarityMetric: ...

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]: ...

    def embed_query(self, text: str) -> EmbeddingVector: ...


class EmbeddingRepository(Protocol):
    """Persist derived embeddings and expose only governed retrieval candidates."""

    def missing_current_chunks(
        self,
        *,
        embedding_strategy_version: str,
        limit: int,
    ) -> tuple[KnowledgeChunk, ...]: ...

    def upsert(self, embeddings: tuple[KnowledgeEmbedding, ...]) -> None: ...

    def eligible_embeddings(
        self,
        *,
        access: RetrievalAccessContext,
        embedding_strategy_version: str,
    ) -> tuple[EmbeddedKnowledgeChunk, ...]: ...
