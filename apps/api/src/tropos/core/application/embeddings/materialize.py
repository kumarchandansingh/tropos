from dataclasses import dataclass
from datetime import UTC, datetime

from tropos.core.application.embeddings.models import KnowledgeEmbedding
from tropos.core.application.ports.embeddings import EmbeddingProvider, EmbeddingRepository


@dataclass(frozen=True, slots=True)
class EmbeddingMaterializationResult:
    """Evidence from one complete materialization pass."""

    embedded_count: int
    strategy_version: str
    model_identifier: str


class MaterializeEmbeddings:
    """Derive missing embeddings after canonical knowledge has already committed."""

    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        repository: EmbeddingRepository,
        batch_size: int = 64,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._provider = provider
        self._repository = repository
        self._batch_size = batch_size

    def execute(self) -> EmbeddingMaterializationResult:
        embedded_count = 0

        while True:
            chunks = self._repository.missing_current_chunks(
                embedding_strategy_version=self._provider.strategy_version,
                limit=self._batch_size,
            )
            if not chunks:
                break

            vectors = self._provider.embed_documents(tuple(chunk.text for chunk in chunks))
            if len(vectors) != len(chunks):
                raise RuntimeError("embedding provider returned an unexpected vector count")

            created_at = datetime.now(UTC)
            embeddings = tuple(
                KnowledgeEmbedding(
                    chunk_id=chunk.chunk_id,
                    embedding_strategy_version=self._provider.strategy_version,
                    model_identifier=self._provider.model_identifier,
                    similarity_metric=self._provider.similarity_metric,
                    vector=vector,
                    created_at=created_at,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            )

            for embedding in embeddings:
                if embedding.vector.dimensions != self._provider.dimensions:
                    raise RuntimeError("embedding dimensions do not match provider contract")

            self._repository.upsert(embeddings)
            embedded_count += len(embeddings)

        return EmbeddingMaterializationResult(
            embedded_count=embedded_count,
            strategy_version=self._provider.strategy_version,
            model_identifier=self._provider.model_identifier,
        )
