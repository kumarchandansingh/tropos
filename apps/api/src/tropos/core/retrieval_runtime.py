"""Compose operational retrieval strategies from runtime settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tropos.core.adapters.embeddings.openai import OpenAIEmbeddingProvider
from tropos.core.adapters.embeddings.sqlite import SQLiteEmbeddingRepository
from tropos.core.adapters.retrieval.exact_vector import ExactVectorKnowledgeRetriever
from tropos.core.adapters.retrieval.hybrid_rrf import HybridRrfKnowledgeRetriever
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.embeddings.materialize import (
    EmbeddingMaterializationResult,
    MaterializeEmbeddings,
)
from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.runtime_config import (
    EmbeddingRuntimeSettings,
    RetrievalStrategy,
)


@dataclass(frozen=True, slots=True)
class RetrievalRuntime:
    retriever: KnowledgeChunkRetriever
    materialization: EmbeddingMaterializationResult | None


def _embedding_provider(settings: EmbeddingRuntimeSettings) -> OpenAIEmbeddingProvider:
    if settings.provider != "openai":
        raise RuntimeError(
            f"unsupported embedding provider: {settings.provider}. "
            "Operational Retrieval V1 currently supports openai."
        )
    return OpenAIEmbeddingProvider(
        api_key=settings.require_api_key(),
        model=settings.model,
        dimensions=settings.dimensions,
    )


def materialize_runtime_embeddings(
    *,
    database_path: str | Path,
    settings: EmbeddingRuntimeSettings,
) -> EmbeddingMaterializationResult:
    provider = _embedding_provider(settings)
    repository = SQLiteEmbeddingRepository(database_path)
    return MaterializeEmbeddings(
        provider=provider,
        repository=repository,
    ).execute()


def build_runtime_retrieval(
    *,
    database_path: str | Path,
    strategy: RetrievalStrategy,
    embedding_settings: EmbeddingRuntimeSettings,
    materialize_missing: bool = False,
) -> RetrievalRuntime:
    lexical = SQLiteFtsKnowledgeRetriever(database_path)
    if strategy is RetrievalStrategy.BM25:
        return RetrievalRuntime(retriever=lexical, materialization=None)

    provider = _embedding_provider(embedding_settings)
    repository = SQLiteEmbeddingRepository(database_path)
    materialization = (
        MaterializeEmbeddings(provider=provider, repository=repository).execute()
        if materialize_missing
        else None
    )
    dense = ExactVectorKnowledgeRetriever(
        provider=provider,
        repository=repository,
    )
    if strategy is RetrievalStrategy.DENSE_EXACT:
        return RetrievalRuntime(retriever=dense, materialization=materialization)
    if strategy is RetrievalStrategy.HYBRID_RRF:
        return RetrievalRuntime(
            retriever=HybridRrfKnowledgeRetriever(
                lexical=lexical,
                dense=dense,
            ),
            materialization=materialization,
        )
    raise AssertionError(f"unsupported retrieval strategy: {strategy}")
