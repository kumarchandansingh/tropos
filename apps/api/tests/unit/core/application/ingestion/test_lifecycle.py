from datetime import UTC, datetime
from pathlib import Path

import pytest

from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.adapters.parsing.deterministic import DeterministicKnowledgeParser
from tropos.core.adapters.persistence.sqlite import SQLiteIngestionStore
from tropos.core.application.ingestion.ingest_knowledge import (
    IngestKnowledge,
    IngestKnowledgeCommand,
)
from tropos.core.application.ingestion.lifecycle import (
    KnowledgeSourceIdentityMismatchError,
    RetireKnowledge,
    RetireKnowledgeCommand,
)
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.ingestion.versioning import KnowledgeLifecycleStatus
from tropos.core.domain.access import AccessPolicy, AccessScope


def _ingest(store: SQLiteIngestionStore) -> None:
    raw = RawKnowledgeRecord(
        source_system="sharepoint:hr",
        source_record_id="item-456",
        source_version="18",
        content_type="text/markdown",
        payload=b"# Remote work\n\nEmployees may work remotely two days.",
        access_policy=AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT),
        captured_at=datetime(2026, 9, 26, tzinfo=UTC),
    )
    IngestKnowledge(
        parser=DeterministicKnowledgeParser(),
        normalizer=DeterministicKnowledgeNormalizer(),
        chunker=DeterministicKnowledgeChunker(max_characters=96),
        source_captures=store,
        knowledge_repository=store,
        runs=store,
    ).execute(IngestKnowledgeCommand(knowledge_id="remote-work", raw_record=raw))


def test_retirement_is_idempotent_and_preserves_canonical_history(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "tropos.db")
    _ingest(store)
    command = RetireKnowledgeCommand(
        knowledge_id="remote-work",
        source_system="sharepoint:hr",
        source_record_id="item-456",
        observed_at=datetime(2026, 9, 27, tzinfo=UTC),
    )

    first = RetireKnowledge(store).execute(command)
    second = RetireKnowledge(store).execute(command)

    assert first.lifecycle_status is KnowledgeLifecycleStatus.DELETED
    assert second == first
    current = store.get_current_state("remote-work")
    assert current is not None
    assert current.lifecycle_status is KnowledgeLifecycleStatus.DELETED


def test_retirement_rejects_wrong_source_identity(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "tropos.db")
    _ingest(store)

    with pytest.raises(KnowledgeSourceIdentityMismatchError):
        RetireKnowledge(store).execute(
            RetireKnowledgeCommand(
                knowledge_id="remote-work",
                source_system="sharepoint:hr",
                source_record_id="item-999",
                observed_at=datetime(2026, 9, 27, tzinfo=UTC),
            )
        )

    current = store.get_current_state("remote-work")
    assert current is not None
    assert current.lifecycle_status is KnowledgeLifecycleStatus.ACTIVE
