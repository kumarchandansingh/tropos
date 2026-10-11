"""Pinned local embedding provider used by reproducible retrieval evaluations."""

from __future__ import annotations

from typing import Any

from sentence_transformers import SentenceTransformer

from tropos.core.application.embeddings.models import EmbeddingVector, SimilarityMetric

MODEL_IDENTIFIER = "sentence-transformers/all-mpnet-base-v2"
MODEL_REVISION = "e8c3b32edf5434bc2275fc9bab85f82640a19130"
STRATEGY_VERSION = "sentence-transformers-all-mpnet-base-v2-normalized-v1"


class SentenceTransformerEmbeddingProvider:
    def __init__(self) -> None:
        self._model = SentenceTransformer(
            MODEL_IDENTIFIER,
            revision=MODEL_REVISION,
        )

    @property
    def strategy_version(self) -> str:
        return STRATEGY_VERSION

    @property
    def model_identifier(self) -> str:
        return MODEL_IDENTIFIER

    @property
    def model_revision(self) -> str:
        return MODEL_REVISION

    @property
    def dimensions(self) -> int:
        dimensions = self._model.get_embedding_dimension()
        if dimensions is None:
            raise RuntimeError("sentence-transformer did not report embedding dimensions")
        return int(dimensions)

    @property
    def similarity_metric(self) -> SimilarityMetric:
        return SimilarityMetric.COSINE

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        return self._encode(texts)

    def embed_query(self, text: str) -> EmbeddingVector:
        return self._encode((text,))[0]

    def _encode(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        vectors: Any = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return tuple(
            EmbeddingVector(tuple(float(value) for value in row.tolist())) for row in vectors
        )
