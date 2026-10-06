from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite

from tropos.core.domain.knowledge_chunk import KnowledgeChunk


class SimilarityMetric(StrEnum):
    """Similarity semantics declared by an embedding strategy."""

    COSINE = "cosine"


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """One finite vector in a provider-specific embedding space."""

    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError("embedding vector must not be empty")
        if any(not isfinite(value) for value in self.values):
            raise ValueError("embedding vector values must be finite")

    @property
    def dimensions(self) -> int:
        return len(self.values)


@dataclass(frozen=True, slots=True)
class KnowledgeEmbedding:
    """Derived embedding lineage for one immutable knowledge chunk."""

    chunk_id: str
    embedding_strategy_version: str
    model_identifier: str
    similarity_metric: SimilarityMetric
    vector: EmbeddingVector
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.chunk_id.strip():
            raise ValueError("chunk_id must not be blank")
        if not self.embedding_strategy_version.strip():
            raise ValueError("embedding_strategy_version must not be blank")
        if not self.model_identifier.strip():
            raise ValueError("model_identifier must not be blank")
        if not isinstance(self.similarity_metric, SimilarityMetric):
            raise TypeError("similarity_metric must be a SimilarityMetric")
        if not isinstance(self.vector, EmbeddingVector):
            raise TypeError("vector must be an EmbeddingVector")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must include timezone information")


@dataclass(frozen=True, slots=True)
class EmbeddedKnowledgeChunk:
    """One governed chunk paired with a compatible derived embedding."""

    chunk: KnowledgeChunk
    embedding: KnowledgeEmbedding

    def __post_init__(self) -> None:
        if self.chunk.chunk_id != self.embedding.chunk_id:
            raise ValueError("embedding chunk_id must match chunk")
