import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.adapters.sources.local_file import LocalFileSourceConnector
from tropos.core.application.ingestion.ingest_from_source import (
    IngestFromSource,
    IngestFromSourceCommand,
)
from tropos.core.application.ingestion.ingest_knowledge import IngestKnowledge
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.ingestion.run_state import IngestionOutcome
from tropos.core.application.ports.sources import (
    SourceCapture,
    SourceCaptureError,
    SourceIdentityMismatchError,
    UnsupportedSourceArtifactError,
)
from tropos.core.domain.access import AccessPolicy, AccessScope


def _policy() -> AccessPolicy:
    return AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT)


def _ingestion(store: SQLiteIngestionStore) -> IngestKnowledge:
    return IngestKnowledge(
        parser=DeterministicKnowledgeParser(),
        normalizer=DeterministicKnowledgeNormalizer(),
        chunker=DeterministicKnowledgeChunker(max_characters=64),
        source_captures=store,
        knowledge_repository=store,
        runs=store,
    )


def test_local_file_connector_feeds_stable_ingestion_boundary(tmp_path: Path) -> None:
    source_root = tmp_path / "knowledge"
    source_root.mkdir()
    article = source_root / "policies" / "reset.md"
    article.parent.mkdir()
    article.write_text("# Reset\n\nUse the secure portal.", encoding="utf-8")

    store = SQLiteIngestionStore(tmp_path / "tropos.db")
    connector = LocalFileSourceConnector(
        root=source_root,
        source_namespace="local:demo-knowledge",
        access_policy=_policy(),
        clock=lambda: datetime(2026, 9, 26, 14, 0, tzinfo=UTC),
    )
    use_case = IngestFromSource(connector=connector, ingestion=_ingestion(store))

    result = use_case.execute(
        IngestFromSourceCommand(
            knowledge_id="password-reset",
            source_record_id="policies/reset.md",
        )
    )

    assert result.outcome is IngestionOutcome.VERSION_CREATED
    assert result.chunks_written > 0

    with sqlite3.connect(tmp_path / "tropos.db") as connection:
        captured = connection.execute(
            """
            SELECT source_system, source_record_id, content_type
            FROM source_captures
            """
        ).fetchone()
        version = connection.execute(
            """
            SELECT source_uri
            FROM knowledge_versions
            WHERE knowledge_id = ?
            """,
            ("password-reset",),
        ).fetchone()

    assert captured == ("local:demo-knowledge", "policies/reset.md", "text/markdown")
    assert version is not None
    assert version[0] == article.resolve().as_uri()


def test_local_source_revision_flows_through_existing_versioning(tmp_path: Path) -> None:
    source_root = tmp_path / "knowledge"
    source_root.mkdir()
    article = source_root / "reset.md"
    article.write_text("# Reset\n\nUse portal A.", encoding="utf-8")

    store = SQLiteIngestionStore(tmp_path / "tropos.db")
    connector = LocalFileSourceConnector(
        root=source_root,
        source_namespace="local:demo-knowledge",
        access_policy=_policy(),
    )
    use_case = IngestFromSource(connector=connector, ingestion=_ingestion(store))
    command = IngestFromSourceCommand(
        knowledge_id="password-reset",
        source_record_id="reset.md",
    )

    first = use_case.execute(command)
    article.write_text("# Reset\n\nUse portal B.", encoding="utf-8")
    second = use_case.execute(command)

    assert first.outcome is IngestionOutcome.VERSION_CREATED
    assert second.outcome is IngestionOutcome.VERSION_CREATED
    assert first.canonical_content_fingerprint != second.canonical_content_fingerprint


def test_local_connector_rejects_paths_outside_configured_root(tmp_path: Path) -> None:
    source_root = tmp_path / "knowledge"
    source_root.mkdir()
    outside = tmp_path / "secret.md"
    outside.write_text("not part of the configured source", encoding="utf-8")

    connector = LocalFileSourceConnector(
        root=source_root,
        source_namespace="local:demo-knowledge",
        access_policy=_policy(),
    )

    with pytest.raises(SourceCaptureError, match="below connector root"):
        connector.capture("../secret.md")


def test_local_connector_rejects_unknown_artifact_type(tmp_path: Path) -> None:
    source_root = tmp_path / "knowledge"
    source_root.mkdir()
    (source_root / "data.csv").write_text("a,b\n1,2", encoding="utf-8")

    connector = LocalFileSourceConnector(
        root=source_root,
        source_namespace="local:demo-knowledge",
        access_policy=_policy(),
    )

    with pytest.raises(UnsupportedSourceArtifactError):
        connector.capture("data.csv")


def test_source_namespace_mismatch_fails_before_ingestion(tmp_path: Path) -> None:
    class MismatchedConnector:
        @property
        def source_namespace(self) -> str:
            return "configured:source"

        def capture(self, source_record_id: str) -> SourceCapture:
            return SourceCapture(
                raw_record=RawKnowledgeRecord(
                    source_system="different:source",
                    source_record_id=source_record_id,
                    source_version="1",
                    content_type="text/plain",
                    payload=b"knowledge",
                    access_policy=_policy(),
                    captured_at=datetime(2026, 9, 26, tzinfo=UTC),
                )
            )

    store = SQLiteIngestionStore(tmp_path / "tropos.db")
    use_case = IngestFromSource(
        connector=MismatchedConnector(),
        ingestion=_ingestion(store),
    )

    with pytest.raises(SourceIdentityMismatchError):
        use_case.execute(
            IngestFromSourceCommand(
                knowledge_id="knowledge-1",
                source_record_id="record-1",
            )
        )
