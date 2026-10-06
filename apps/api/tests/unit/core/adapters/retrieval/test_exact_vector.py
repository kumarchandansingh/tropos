from datetime import UTC, datetime
from pathlib import Path

from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.adapters.embeddings.sqlite import SQLiteEmbeddingRepository
from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.adapters.retrieval.exact_vector import ExactVectorKnowledgeRetriever
from tropos.core.application.embeddings.materialize import MaterializeEmbeddings
from tropos.core.application.embeddings.models import EmbeddingVector, SimilarityMetric
from tropos.core.application.ingestion.ingest_knowledge import (
    IngestKnowledge,
    IngestKnowledgeCommand,
)
from tropos.core.application.ingestion.lifecycle import RetireKnowledge, RetireKnowledgeCommand
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
)
from tropos.core.domain.access import AccessPolicy, AccessScope


class _FakeEmbeddingProvider:
    def __init__(self, strategy_version: str = "fake-semantic-v1") -> None:
        self._strategy_version = strategy_version
        self.document_calls = 0

    @property
    def strategy_version(self) -> str:
        return self._strategy_version

    @property
    def model_identifier(self) -> str:
        return "fake-semantic-model"

    @property
    def dimensions(self) -> int:
        return 2

    @property
    def similarity_metric(self) -> SimilarityMetric:
        return SimilarityMetric.COSINE

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        self.document_calls += 1
        return tuple(self._vector(text) for text in texts)

    def embed_query(self, text: str) -> EmbeddingVector:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> EmbeddingVector:
        lowered = text.casefold()
        if (
            "remote work" in lowered
            or "away from company premises" in lowered
            or "flexible location" in lowered
        ):
            return EmbeddingVector((1.0, 0.0))
        if "priority-one" in lowered or "coordination bridge" in lowered:
            return EmbeddingVector((0.0, 1.0))
        return EmbeddingVector((0.5, 0.5))


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
    raw = RawKnowledgeRecord(
        source_system="test-kb",
        source_record_id=f"{knowledge_id}.md",
        source_version="1",
        content_type="text/markdown",
        payload=text.encode("utf-8"),
        access_policy=access_policy,
        captured_at=datetime(2026, 10, 6, tzinfo=UTC),
    )
    orchestrator.execute(IngestKnowledgeCommand(knowledge_id=knowledge_id, raw_record=raw))


def _search(
    retriever: ExactVectorKnowledgeRetriever,
    query: str,
    *,
    groups: tuple[str, ...] = (),
) -> tuple[str, ...]:
    results = retriever.search(
        KnowledgeSearchRequest(
            query=query,
            access=RetrievalAccessContext(tenant_id="tenant-a", groups=groups),
            limit=5,
        )
    )
    return tuple(result.chunk.knowledge_id for result in results)


def test_exact_dense_retrieval_recovers_semantic_paraphrase(tmp_path: Path) -> None:
    database = tmp_path / "tropos.db"
    store = SQLiteIngestionStore(database)
    orchestrator = _orchestrator(store)
    access = AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT)

    _ingest(
        orchestrator,
        knowledge_id="flexible-location-guidance",
        text=(
            "# Flexible location guidance\n\n"
            "Employees may perform their duties away from company premises "
            "for up to two days each week."
        ),
        access_policy=access,
    )
    _ingest(
        orchestrator,
        knowledge_id="unrelated",
        text="# Expense claim\n\nAttach the hotel receipt before reimbursement.",
        access_policy=access,
    )

    repository = SQLiteEmbeddingRepository(database)
    provider = _FakeEmbeddingProvider()
    result = MaterializeEmbeddings(provider=provider, repository=repository).execute()
    retriever = ExactVectorKnowledgeRetriever(provider=provider, repository=repository)

    assert result.embedded_count == 2
    assert _search(retriever, "remote work policy")[0] == "flexible-location-guidance"


def test_materialization_is_idempotent_per_embedding_strategy(tmp_path: Path) -> None:
    database = tmp_path / "tropos.db"
    store = SQLiteIngestionStore(database)
    _ingest(
        _orchestrator(store),
        knowledge_id="article",
        text="# Article\n\nSome useful knowledge.",
        access_policy=AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT),
    )
    repository = SQLiteEmbeddingRepository(database)
    provider = _FakeEmbeddingProvider()

    first = MaterializeEmbeddings(provider=provider, repository=repository).execute()
    second = MaterializeEmbeddings(provider=provider, repository=repository).execute()
    another_strategy = _FakeEmbeddingProvider("fake-semantic-v2")
    third = MaterializeEmbeddings(
        provider=another_strategy,
        repository=repository,
    ).execute()

    assert first.embedded_count == 1
    assert second.embedded_count == 0
    assert provider.document_calls == 1
    assert third.embedded_count == 1


def test_dense_retrieval_enforces_acl_before_similarity_ranking(tmp_path: Path) -> None:
    database = tmp_path / "tropos.db"
    store = SQLiteIngestionStore(database)
    orchestrator = _orchestrator(store)
    restricted = AccessPolicy(
        tenant_id="tenant-a",
        scope=AccessScope.RESTRICTED,
        allowed_groups=("support-leads",),
    )
    _ingest(
        orchestrator,
        knowledge_id="priority-incident",
        text="# Priority incident\n\nOpen the coordination bridge for a priority-one outage.",
        access_policy=restricted,
    )

    repository = SQLiteEmbeddingRepository(database)
    provider = _FakeEmbeddingProvider()
    MaterializeEmbeddings(provider=provider, repository=repository).execute()
    retriever = ExactVectorKnowledgeRetriever(provider=provider, repository=repository)

    assert _search(retriever, "priority-one coordination bridge") == ()
    assert _search(
        retriever,
        "priority-one coordination bridge",
        groups=("support-leads",),
    ) == ("priority-incident",)


def test_dense_retrieval_excludes_deleted_knowledge_without_deleting_embedding(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tropos.db"
    store = SQLiteIngestionStore(database)
    orchestrator = _orchestrator(store)
    _ingest(
        orchestrator,
        knowledge_id="flexible-location-guidance",
        text=(
            "# Flexible location guidance\n\n"
            "Employees may perform their duties away from company premises."
        ),
        access_policy=AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT),
    )

    repository = SQLiteEmbeddingRepository(database)
    provider = _FakeEmbeddingProvider()
    MaterializeEmbeddings(provider=provider, repository=repository).execute()
    retriever = ExactVectorKnowledgeRetriever(provider=provider, repository=repository)
    assert _search(retriever, "remote work policy") == ("flexible-location-guidance",)

    RetireKnowledge(store).execute(
        RetireKnowledgeCommand(
            knowledge_id="flexible-location-guidance",
            source_system="test-kb",
            source_record_id="flexible-location-guidance.md",
            observed_at=datetime(2026, 10, 7, tzinfo=UTC),
        )
    )

    assert _search(retriever, "remote work policy") == ()
    assert (
        repository.missing_current_chunks(
            embedding_strategy_version=provider.strategy_version,
            limit=10,
        )
        == ()
    )
