from math import sqrt

from tropos.core.application.embeddings.models import (
    EmbeddedKnowledgeChunk,
    EmbeddingVector,
    SimilarityMetric,
)
from tropos.core.application.ports.embeddings import EmbeddingProvider, EmbeddingRepository
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievedKnowledgeChunk,
)


class ExactVectorKnowledgeRetriever:
    """Governed exact semantic retrieval over one compatible embedding space."""

    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        repository: EmbeddingRepository,
    ) -> None:
        if provider.similarity_metric is not SimilarityMetric.COSINE:
            raise ValueError("V1 exact retriever currently supports cosine similarity only")
        self._provider = provider
        self._repository = repository

    @property
    def strategy_version(self) -> str:
        return f"dense-exact-cosine-v1:{self._provider.strategy_version}"

    def search(self, request: KnowledgeSearchRequest) -> tuple[RetrievedKnowledgeChunk, ...]:
        if not isinstance(request, KnowledgeSearchRequest):
            raise TypeError("request must be a KnowledgeSearchRequest")

        query_vector = self._provider.embed_query(request.query)
        if query_vector.dimensions != self._provider.dimensions:
            raise RuntimeError("query embedding dimensions do not match provider contract")

        candidates = self._repository.eligible_embeddings(
            access=request.access,
            embedding_strategy_version=self._provider.strategy_version,
        )

        scored: list[tuple[float, str, int, EmbeddedKnowledgeChunk]] = []
        for candidate in candidates:
            embedding = candidate.embedding
            if embedding.model_identifier != self._provider.model_identifier:
                raise RuntimeError("stored embedding model does not match provider")
            if embedding.similarity_metric is not self._provider.similarity_metric:
                raise RuntimeError("stored embedding similarity metric does not match provider")
            if embedding.vector.dimensions != query_vector.dimensions:
                raise RuntimeError("stored embedding dimensions do not match query")
            score = _cosine_similarity(query_vector, embedding.vector)
            scored.append(
                (
                    score,
                    candidate.chunk.knowledge_id,
                    candidate.chunk.sequence_number,
                    candidate,
                )
            )

        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        selected = scored[: request.limit]

        return tuple(
            RetrievedKnowledgeChunk(
                chunk=candidate.chunk,
                rank=rank,
                score=score,
                strategy_version=self.strategy_version,
            )
            for rank, (score, _, _, candidate) in enumerate(selected, start=1)
        )


def _cosine_similarity(left: EmbeddingVector, right: EmbeddingVector) -> float:
    if left.dimensions != right.dimensions:
        raise ValueError("cosine similarity requires equal dimensions")

    dot = sum(a * b for a, b in zip(left.values, right.values, strict=True))
    left_norm = sqrt(sum(value * value for value in left.values))
    right_norm = sqrt(sum(value * value for value in right.values))
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("cosine similarity is undefined for a zero vector")
    return dot / (left_norm * right_norm)
