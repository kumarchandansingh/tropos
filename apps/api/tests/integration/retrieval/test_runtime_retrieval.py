from pathlib import Path

import pytest

from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.retrieval_runtime import build_runtime_retrieval
from tropos.core.runtime_config import EmbeddingRuntimeSettings, RetrievalStrategy


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "tropos.db"
    SQLiteIngestionStore(database)
    return database


def test_runtime_builder_keeps_bm25_available_without_embedding_secret(
    tmp_path: Path,
) -> None:
    runtime = build_runtime_retrieval(
        database_path=_database(tmp_path),
        strategy=RetrievalStrategy.BM25,
        embedding_settings=EmbeddingRuntimeSettings(),
    )

    assert runtime.materialization is None
    assert runtime.retriever.strategy_version == "sqlite-fts5-bm25-v1"


@pytest.mark.parametrize(
    "strategy",
    (RetrievalStrategy.DENSE_EXACT, RetrievalStrategy.HYBRID_RRF),
)
def test_semantic_runtime_fails_closed_without_embedding_secret(
    tmp_path: Path,
    strategy: RetrievalStrategy,
) -> None:
    with pytest.raises(RuntimeError, match="TROPOS_OPENAI_API_KEY"):
        build_runtime_retrieval(
            database_path=_database(tmp_path),
            strategy=strategy,
            embedding_settings=EmbeddingRuntimeSettings(),
        )


def test_semantic_runtime_composes_existing_dense_and_hybrid_adapters_without_network(
    tmp_path: Path,
) -> None:
    settings = EmbeddingRuntimeSettings(api_key="sk-test")

    dense = build_runtime_retrieval(
        database_path=_database(tmp_path),
        strategy=RetrievalStrategy.DENSE_EXACT,
        embedding_settings=settings,
        materialize_missing=False,
    )
    hybrid = build_runtime_retrieval(
        database_path=_database(tmp_path),
        strategy=RetrievalStrategy.HYBRID_RRF,
        embedding_settings=settings,
        materialize_missing=False,
    )

    assert dense.retriever.strategy_version.startswith("dense-exact-cosine-v1:")
    assert hybrid.retriever.strategy_version.startswith("hybrid-rrf-v1:")
