from __future__ import annotations

from pathlib import Path

from tropos.cli import ingest_local_file
from tropos.core.adapters.retrieval.sqlite_fts import SQLiteFtsKnowledgeRetriever
from tropos.core.application.ingestion.run_state import IngestionOutcome
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievalAccessContext,
)


def test_ingest_file_creates_searchable_current_knowledge(tmp_path: Path) -> None:
    source = tmp_path / "runbook.md"
    source.write_text(
        "# Certificate rotation\n\nRestart the device after certificate rotation.",
        encoding="utf-8",
    )
    database = tmp_path / "tropos.db"

    result = ingest_local_file(
        file_path=source,
        database_path=database,
        tenant_id="tenant-a",
    )

    assert result.outcome is IngestionOutcome.VERSION_CREATED
    assert result.chunks_written > 0

    retrieved = SQLiteFtsKnowledgeRetriever(database).search(
        KnowledgeSearchRequest(
            query="certificate rotation",
            access=RetrievalAccessContext(tenant_id="tenant-a"),
        )
    )
    assert retrieved
    assert retrieved[0].chunk.knowledge_id == result.knowledge_id


def test_reingest_formatting_only_change_does_not_create_content_version(tmp_path: Path) -> None:
    source = tmp_path / "procedure.md"
    source.write_text("# Reset\n\nRestart the service.", encoding="utf-8")
    database = tmp_path / "tropos.db"

    first = ingest_local_file(
        file_path=source,
        database_path=database,
        tenant_id="tenant-a",
    )

    source.write_text("# Reset  \n\n\nRestart the service.   \n", encoding="utf-8")
    second = ingest_local_file(
        file_path=source,
        database_path=database,
        tenant_id="tenant-a",
        knowledge_id=first.knowledge_id,
    )

    assert first.outcome is IngestionOutcome.VERSION_CREATED
    assert second.outcome is IngestionOutcome.NO_CHANGE
    assert second.chunks_written == 0


def test_restricted_file_is_not_retrieved_without_matching_group(tmp_path: Path) -> None:
    source = tmp_path / "restricted.txt"
    source.write_text("Escalation token recovery procedure", encoding="utf-8")
    database = tmp_path / "tropos.db"

    ingest_local_file(
        file_path=source,
        database_path=database,
        tenant_id="tenant-a",
        groups=("support-l3",),
    )

    retriever = SQLiteFtsKnowledgeRetriever(database)
    denied = retriever.search(
        KnowledgeSearchRequest(
            query="escalation recovery",
            access=RetrievalAccessContext(tenant_id="tenant-a", groups=("support-l2",)),
        )
    )
    allowed = retriever.search(
        KnowledgeSearchRequest(
            query="escalation recovery",
            access=RetrievalAccessContext(tenant_id="tenant-a", groups=("support-l3",)),
        )
    )

    assert denied == ()
    assert allowed
