from datetime import UTC, datetime
from pathlib import Path

from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.ingestion.ingest_knowledge import (
    IngestKnowledge,
    IngestKnowledgeCommand,
)
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
)
from tropos.core.domain.access import AccessPolicy, AccessScope


def _orchestrator(store: SQLiteIngestionStore) -> IngestKnowledge:
    return IngestKnowledge(
        parser=DeterministicKnowledgeParser(),
        normalizer=DeterministicKnowledgeNormalizer(),
        chunker=DeterministicKnowledgeChunker(max_characters=96),
        source_captures=store,
        knowledge_repository=store,
        runs=store,
    )


def _ingest(
    orchestrator: IngestKnowledge,
    *,
    knowledge_id: str,
    text: str,
    source_version: str,
    access_policy: AccessPolicy,
) -> None:
    raw = RawKnowledgeRecord(
        source_system="test-kb",
        source_record_id=f"{knowledge_id}.md",
        source_version=source_version,
        content_type="text/markdown",
        payload=text.encode("utf-8"),
        access_policy=access_policy,
        captured_at=datetime(2026, 9, 26, tzinfo=UTC),
    )
    orchestrator.execute(IngestKnowledgeCommand(knowledge_id=knowledge_id, raw_record=raw))


def _search(
    retriever: SQLiteFtsKnowledgeRetriever,
    query: str,
    *,
    tenant_id: str = "tenant-a",
    groups: tuple[str, ...] = (),
) -> tuple[str, ...]:
    results = retriever.search(
        KnowledgeSearchRequest(
            query=query,
            access=RetrievalAccessContext(tenant_id=tenant_id, groups=groups),
            limit=10,
        )
    )
    return tuple(result.chunk.knowledge_id for result in results)


def test_lexical_retrieval_returns_ranked_current_chunks_for_tenant(tmp_path: Path) -> None:
    database = tmp_path / "tropos.db"
    store = SQLiteIngestionStore(database)
    orchestrator = _orchestrator(store)
    tenant_access = AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT)

    _ingest(
        orchestrator,
        knowledge_id="password-reset",
        text="# Password reset\n\nUse the secure recovery portal for MFA reset.",
        source_version="1",
        access_policy=tenant_access,
    )
    _ingest(
        orchestrator,
        knowledge_id="shipping-policy",
        text="# Shipping\n\nExpedited parcels use the priority carrier.",
        source_version="1",
        access_policy=tenant_access,
    )

    retriever = SQLiteFtsKnowledgeRetriever(database)
    results = retriever.search(
        KnowledgeSearchRequest(
            query="MFA recovery",
            access=RetrievalAccessContext(tenant_id="tenant-a"),
            limit=5,
        )
    )

    assert results
    assert results[0].chunk.knowledge_id == "password-reset"
    assert results[0].rank == 1
    assert results[0].strategy_version == "sqlite-fts5-bm25-v1"
    assert _search(retriever, "MFA recovery", tenant_id="tenant-b") == ()


def test_restricted_chunks_require_group_membership_inside_retrieval(tmp_path: Path) -> None:
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
        knowledge_id="incident-runbook",
        text="# Incident runbook\n\nEscalate the sev-one incident to the command bridge.",
        source_version="1",
        access_policy=restricted,
    )

    retriever = SQLiteFtsKnowledgeRetriever(database)

    assert _search(retriever, "command bridge") == ()
    assert _search(retriever, "command bridge", groups=("support-agents",)) == ()
    assert _search(retriever, "command bridge", groups=("support-leads",)) == ("incident-runbook",)


def test_historical_chunks_remain_stored_but_are_not_retrieved(tmp_path: Path) -> None:
    database = tmp_path / "tropos.db"
    store = SQLiteIngestionStore(database)
    orchestrator = _orchestrator(store)
    access = AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT)

    _ingest(
        orchestrator,
        knowledge_id="reset-guide",
        text="# Reset guide\n\nThe legacy zebra workflow resets credentials.",
        source_version="1",
        access_policy=access,
    )
    _ingest(
        orchestrator,
        knowledge_id="reset-guide",
        text="# Reset guide\n\nThe modern phoenix workflow resets credentials.",
        source_version="2",
        access_policy=access,
    )

    retriever = SQLiteFtsKnowledgeRetriever(database)

    assert _search(retriever, "zebra") == ()
    assert _search(retriever, "phoenix") == ("reset-guide",)


def test_fts_triggers_index_chunks_created_after_retriever_initialization(tmp_path: Path) -> None:
    database = tmp_path / "tropos.db"
    store = SQLiteIngestionStore(database)
    retriever = SQLiteFtsKnowledgeRetriever(database)
    orchestrator = _orchestrator(store)

    _ingest(
        orchestrator,
        knowledge_id="after-startup",
        text="# Later knowledge\n\nOrchid synchronization is available after startup.",
        source_version="1",
        access_policy=AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT),
    )

    assert _search(retriever, "orchid synchronization") == ("after-startup",)
