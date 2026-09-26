import sqlite3
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
from tropos.core.application.ingestion.parsing import UnsupportedContentTypeError
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.ingestion.run_state import IngestionOutcome
from tropos.core.application.ingestion.versioning import (
    VersionAction,
    access_policy_fingerprint,
)
from tropos.core.domain.access import AccessPolicy, AccessScope


def _raw(
    text: str,
    *,
    source_version: str,
    access_policy: AccessPolicy | None = None,
    content_type: str = "text/markdown",
) -> RawKnowledgeRecord:
    return RawKnowledgeRecord(
        source_system="test-kb",
        source_record_id="article-42",
        source_version=source_version,
        content_type=content_type,
        payload=text.encode("utf-8"),
        access_policy=access_policy or AccessPolicy(tenant_id="tenant-a", scope=AccessScope.TENANT),
        captured_at=datetime(2026, 9, 26, tzinfo=UTC),
    )


def _orchestrator(
    store: SQLiteIngestionStore,
    *,
    normalizer_version: str = "canonical-text-v1",
) -> IngestKnowledge:
    return IngestKnowledge(
        parser=DeterministicKnowledgeParser(),
        normalizer=DeterministicKnowledgeNormalizer(strategy_version=normalizer_version),
        chunker=DeterministicKnowledgeChunker(max_characters=64),
        source_captures=store,
        knowledge_repository=store,
        runs=store,
    )


def test_orchestrator_runs_versioning_governance_and_idempotency(tmp_path: Path) -> None:
    database = tmp_path / "tropos.db"
    store = SQLiteIngestionStore(database)
    orchestrator = _orchestrator(store)

    first_raw = _raw(
        "# Password Reset\n\nUse the portal.\n\n- Verify identity",
        source_version="1",
    )
    first = orchestrator.execute(
        IngestKnowledgeCommand(knowledge_id="knowledge-42", raw_record=first_raw)
    )

    assert first.outcome is IngestionOutcome.VERSION_CREATED
    assert first.action is VersionAction.CREATE_VERSION
    assert first.chunks_written > 0
    assert first.governance_refreshed is False

    replay = orchestrator.execute(
        IngestKnowledgeCommand(knowledge_id="knowledge-42", raw_record=first_raw)
    )
    assert replay.run_id == first.run_id
    assert replay.replayed is True

    formatting_only = _raw(
        "\ufeff# Password Reset\r\n\r\nUse the portal.   \r\n\r\n* Verify identity\r\n",
        source_version="2",
    )
    unchanged = orchestrator.execute(
        IngestKnowledgeCommand(knowledge_id="knowledge-42", raw_record=formatting_only)
    )
    assert unchanged.outcome is IngestionOutcome.NO_CHANGE
    assert unchanged.chunks_written == 0

    restricted = AccessPolicy(
        tenant_id="tenant-a",
        scope=AccessScope.RESTRICTED,
        allowed_groups=("support-leads",),
    )
    access_change = _raw(
        "# Password Reset\n\nUse the portal.\n\n- Verify identity",
        source_version="3",
        access_policy=restricted,
    )
    governance = orchestrator.execute(
        IngestKnowledgeCommand(knowledge_id="knowledge-42", raw_record=access_change)
    )
    assert governance.outcome is IngestionOutcome.GOVERNANCE_REFRESHED
    assert governance.governance_refreshed is True

    state = store.get_current_state("knowledge-42")
    assert state is not None
    assert state.access_fingerprint == access_policy_fingerprint(restricted)

    changed = _raw(
        "# Password Reset\n\nUse the secure portal.\n\n- Verify identity",
        source_version="4",
        access_policy=restricted,
    )
    second_version = orchestrator.execute(
        IngestKnowledgeCommand(knowledge_id="knowledge-42", raw_record=changed)
    )
    assert second_version.outcome is IngestionOutcome.VERSION_CREATED
    assert second_version.governance_refreshed is False

    with sqlite3.connect(database) as connection:
        version_count = connection.execute(
            "SELECT COUNT(*) FROM knowledge_versions WHERE knowledge_id = ?",
            ("knowledge-42",),
        ).fetchone()
        run_count = connection.execute(
            "SELECT COUNT(*) FROM ingestion_runs WHERE knowledge_id = ?",
            ("knowledge-42",),
        ).fetchone()

    assert version_count == (2,)
    assert run_count == (4,)


def test_rebaseline_is_recorded_without_replacing_current_state(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "tropos.db")

    first = _orchestrator(store).execute(
        IngestKnowledgeCommand(
            knowledge_id="knowledge-42",
            raw_record=_raw("# Reset\n\nUse the portal.", source_version="1"),
        )
    )
    assert first.outcome is IngestionOutcome.VERSION_CREATED

    rebaseline = _orchestrator(
        store,
        normalizer_version="canonical-text-v2",
    ).execute(
        IngestKnowledgeCommand(
            knowledge_id="knowledge-42",
            raw_record=_raw("# Reset\n\nUse the portal.", source_version="2"),
        )
    )

    assert rebaseline.outcome is IngestionOutcome.REBASELINE_REQUIRED
    state = store.get_current_state("knowledge-42")
    assert state is not None
    assert state.normalization_strategy_version == "canonical-text-v1"


def test_parser_failure_is_persisted_as_failed_run(tmp_path: Path) -> None:
    database = tmp_path / "tropos.db"
    store = SQLiteIngestionStore(database)
    orchestrator = _orchestrator(store)
    raw = _raw("%PDF-1.7", source_version="1", content_type="application/pdf")

    with pytest.raises(UnsupportedContentTypeError):
        orchestrator.execute(IngestKnowledgeCommand(knowledge_id="knowledge-pdf", raw_record=raw))

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            """
            SELECT status, stage, error_type
            FROM ingestion_runs
            WHERE knowledge_id = ?
            """,
            ("knowledge-pdf",),
        ).fetchone()

    assert row == ("FAILED", "FAILED", "UnsupportedContentTypeError")
