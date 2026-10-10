from datetime import UTC, datetime
from pathlib import Path

import pytest

from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.adapters.embeddings.sqlite import SQLiteEmbeddingRepository
from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.adapters.retrieval.exact_vector import ExactVectorKnowledgeRetriever
from tropos.core.adapters.retrieval.hybrid_rrf import HybridRrfKnowledgeRetriever
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.embeddings.materialize import MaterializeEmbeddings
from tropos.core.application.embeddings.models import EmbeddingVector, SimilarityMetric
from tropos.core.application.ingestion.ingest_knowledge import (
    IngestKnowledge,
    IngestKnowledgeCommand,
)
from tropos.core.application.ingestion.lifecycle import RetireKnowledge, RetireKnowledgeCommand
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.ports.retrieval import KnowledgeChunkRetriever
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
    RetrievedKnowledgeChunk,
)
from tropos.core.domain.access import AccessPolicy, AccessScope


class _ContractEmbeddingProvider:
    @property
    def strategy_version(self) -> str:
        return "contract-embedding-v1"

    @property
    def model_identifier(self) -> str:
        return "contract-embedding"

    @property
    def dimensions(self) -> int:
        return 4

    @property
    def similarity_metric(self) -> SimilarityMetric:
        return SimilarityMetric.COSINE

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        return tuple(self._vector(text) for text in texts)

    def embed_query(self, text: str) -> EmbeddingVector:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> EmbeddingVector:
        lowered = text.casefold()
        if "orchid" in lowered:
            return EmbeddingVector((1.0, 0.0, 0.0, 0.0))
        if "citadel" in lowered:
            return EmbeddingVector((0.0, 1.0, 0.0, 0.0))
        if "nebula" in lowered:
            return EmbeddingVector((0.0, 0.0, 1.0, 0.0))
        if "lavender" in lowered:
            return EmbeddingVector((0.0, 0.0, 0.0, 1.0))
        return EmbeddingVector((0.5, 0.5, 0.5, 0.5))


def _orchestrator(store: SQLiteIngestionStore) -> IngestKnowledge:
    return IngestKnowledge(
        parser=DeterministicKnowledgeParser(),
        normalizer=DeterministicKnowledgeNormalizer(),
        chunker=DeterministicKnowledgeChunker(max_characters=2000),
        source_captures=store,
        knowledge_repository=store,
        runs=store,
    )


def _ingest(
    orchestrator: IngestKnowledge,
    *,
    knowledge_id: str,
    text: str,
    access_policy: AccessPolicy,
) -> None:
    orchestrator.execute(
        IngestKnowledgeCommand(
            knowledge_id=knowledge_id,
            raw_record=RawKnowledgeRecord(
                source_system="contract-kb",
                source_record_id=f"{knowledge_id}.md",
                source_version="1",
                content_type="text/markdown",
                payload=text.encode("utf-8"),
                access_policy=access_policy,
                captured_at=datetime(2026, 10, 10, tzinfo=UTC),
            ),
        )
    )


def _fixture_database(path: Path) -> Path:
    database = path / "tropos.db"
    store = SQLiteIngestionStore(database)
    orchestrator = _orchestrator(store)
    tenant_a = AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT)

    _ingest(
        orchestrator,
        knowledge_id="orchid-guide",
        text="# Orchid recovery\n\nUse the orchid recovery procedure.",
        access_policy=tenant_a,
    )
    _ingest(
        orchestrator,
        knowledge_id="citadel-runbook",
        text="# Citadel incident\n\nOpen the citadel coordination bridge.",
        access_policy=AccessPolicy(
            tenant_id="tenant-a",
            scope=AccessScope.RESTRICTED,
            allowed_groups=("support-leads",),
        ),
    )
    _ingest(
        orchestrator,
        knowledge_id="nebula-secret",
        text="# Nebula procedure\n\nUse the nebula tenant-only procedure.",
        access_policy=AccessPolicy(tenant_id="tenant-b", scope=AccessScope.TENANT),
    )
    _ingest(
        orchestrator,
        knowledge_id="lavender-obsolete",
        text="# Lavender legacy\n\nUse the lavender recovery procedure.",
        access_policy=tenant_a,
    )

    repository = SQLiteEmbeddingRepository(database)
    provider = _ContractEmbeddingProvider()
    MaterializeEmbeddings(provider=provider, repository=repository).execute()

    RetireKnowledge(store).execute(
        RetireKnowledgeCommand(
            knowledge_id="lavender-obsolete",
            source_system="contract-kb",
            source_record_id="lavender-obsolete.md",
            observed_at=datetime(2026, 10, 11, tzinfo=UTC),
        )
    )
    return database


def _retriever(database: Path, strategy: str) -> KnowledgeChunkRetriever:
    lexical = SQLiteFtsKnowledgeRetriever(database)
    if strategy == "bm25":
        return lexical

    provider = _ContractEmbeddingProvider()
    dense = ExactVectorKnowledgeRetriever(
        provider=provider,
        repository=SQLiteEmbeddingRepository(database),
    )
    if strategy == "dense":
        return dense
    if strategy == "hybrid":
        return HybridRrfKnowledgeRetriever(lexical=lexical, dense=dense)
    raise AssertionError(f"unknown test strategy: {strategy}")


def _search(
    retriever: KnowledgeChunkRetriever,
    query: str,
    *,
    tenant_id: str = "tenant-a",
    groups: tuple[str, ...] = (),
) -> tuple[RetrievedKnowledgeChunk, ...]:
    return retriever.search(
        KnowledgeSearchRequest(
            query=query,
            access=RetrievalAccessContext(tenant_id=tenant_id, groups=groups),
            limit=5,
        )
    )


@pytest.mark.parametrize("strategy", ("bm25", "dense", "hybrid"))
def test_retrievers_never_return_cross_tenant_evidence(
    tmp_path: Path,
    strategy: str,
) -> None:
    retriever = _retriever(_fixture_database(tmp_path), strategy)

    results = _search(retriever, "nebula procedure")

    assert all(result.chunk.knowledge_id != "nebula-secret" for result in results)
    assert all(result.chunk.access_policy.tenant_id == "tenant-a" for result in results)


@pytest.mark.parametrize("strategy", ("bm25", "dense", "hybrid"))
def test_retrievers_enforce_restricted_group_membership(
    tmp_path: Path,
    strategy: str,
) -> None:
    retriever = _retriever(_fixture_database(tmp_path), strategy)

    unauthorized = _search(retriever, "citadel coordination bridge")
    authorized = _search(
        retriever,
        "citadel coordination bridge",
        groups=("support-leads",),
    )

    assert all(result.chunk.knowledge_id != "citadel-runbook" for result in unauthorized)
    assert authorized[0].chunk.knowledge_id == "citadel-runbook"


@pytest.mark.parametrize("strategy", ("bm25", "dense", "hybrid"))
def test_retrievers_exclude_deleted_knowledge(
    tmp_path: Path,
    strategy: str,
) -> None:
    retriever = _retriever(_fixture_database(tmp_path), strategy)

    results = _search(retriever, "lavender recovery")

    assert all(result.chunk.knowledge_id != "lavender-obsolete" for result in results)


@pytest.mark.parametrize("strategy", ("bm25", "dense", "hybrid"))
def test_retrievers_return_unique_chunks_with_consecutive_ranks(
    tmp_path: Path,
    strategy: str,
) -> None:
    retriever = _retriever(_fixture_database(tmp_path), strategy)

    results = _search(retriever, "orchid recovery")

    assert results
    assert [result.rank for result in results] == list(range(1, len(results) + 1))
    chunk_ids = [result.chunk.chunk_id for result in results]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert all(result.strategy_version == retriever.strategy_version for result in results)
