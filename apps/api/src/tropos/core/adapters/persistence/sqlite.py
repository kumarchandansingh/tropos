import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.application.ingestion.run_state import (
    IngestionOutcome,
    IngestionResult,
    IngestionStage,
)
from tropos.core.application.ingestion.versioning import (
    CanonicalKnowledgeState,
    VersionAction,
    VersionReason,
    access_policy_fingerprint,
)
from tropos.core.application.ports.persistence import (
    ConcurrentKnowledgeUpdateError,
    IngestionAlreadyInProgressError,
)
from tropos.core.domain.access import AccessPolicy
from tropos.core.domain.knowledge import KnowledgeDocument
from tropos.core.domain.knowledge_chunk import KnowledgeChunk


class SQLiteIngestionStore:
    """SQLite implementation of source capture, ingestion runs, and canonical state."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS source_captures (
                    ingestion_fingerprint TEXT PRIMARY KEY,
                    raw_payload_fingerprint TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    tenant_id TEXT NOT NULL,
                    access_scope TEXT NOT NULL,
                    allowed_groups_json TEXT NOT NULL,
                    captured_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_state (
                    knowledge_id TEXT PRIMARY KEY,
                    content_fingerprint TEXT NOT NULL,
                    normalization_strategy_version TEXT NOT NULL,
                    access_fingerprint TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_versions (
                    knowledge_id TEXT NOT NULL,
                    content_fingerprint TEXT NOT NULL,
                    normalization_strategy_version TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    access_scope TEXT NOT NULL,
                    allowed_groups_json TEXT NOT NULL,
                    raw_payload_fingerprint TEXT NOT NULL,
                    ingestion_fingerprint TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    source_uri TEXT,
                    source_updated_at TEXT,
                    PRIMARY KEY (
                        knowledge_id,
                        content_fingerprint,
                        normalization_strategy_version
                    )
                );

                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    document_title TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    content_fingerprint TEXT NOT NULL,
                    ingestion_fingerprint TEXT NOT NULL,
                    normalized_content_fingerprint TEXT NOT NULL,
                    normalization_strategy_version TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    access_scope TEXT NOT NULL,
                    allowed_groups_json TEXT NOT NULL,
                    chunking_strategy_version TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_knowledge_version
                ON knowledge_chunks (
                    knowledge_id,
                    normalized_content_fingerprint,
                    normalization_strategy_version
                );

                CREATE TABLE IF NOT EXISTS ingestion_runs (
                    run_id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    ingestion_fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    outcome TEXT,
                    version_action TEXT,
                    version_reason TEXT,
                    canonical_content_fingerprint TEXT,
                    chunks_written INTEGER NOT NULL DEFAULT 0,
                    governance_refreshed INTEGER NOT NULL DEFAULT 0,
                    error_type TEXT,
                    error_message TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE (knowledge_id, ingestion_fingerprint)
                );
                """
            )

    def record(self, raw_record: RawKnowledgeRecord) -> None:
        policy = raw_record.access_policy
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO source_captures (
                    ingestion_fingerprint,
                    raw_payload_fingerprint,
                    source_system,
                    source_record_id,
                    source_version,
                    content_type,
                    payload,
                    tenant_id,
                    access_scope,
                    allowed_groups_json,
                    captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    raw_record.ingestion_fingerprint,
                    raw_record.raw_payload_fingerprint,
                    raw_record.source_system,
                    raw_record.source_record_id,
                    raw_record.source_version,
                    raw_record.content_type,
                    raw_record.payload,
                    policy.tenant_id,
                    policy.scope.value,
                    json.dumps(policy.allowed_groups, separators=(",", ":")),
                    raw_record.captured_at.isoformat(),
                ),
            )

    def get_current_state(self, knowledge_id: str) -> CanonicalKnowledgeState | None:
        with self._connect() as connection:
            return self._load_state(connection, knowledge_id)

    def refresh_governance(
        self,
        *,
        knowledge_id: str,
        access_policy: AccessPolicy,
        expected_state: CanonicalKnowledgeState,
    ) -> CanonicalKnowledgeState:
        new_access_fingerprint = access_policy_fingerprint(access_policy)
        groups = json.dumps(access_policy.allowed_groups, separators=(",", ":"))

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_state(connection, knowledge_id)
            if current != expected_state:
                raise ConcurrentKnowledgeUpdateError(
                    f"canonical state changed before governance refresh: {knowledge_id}"
                )

            version_cursor = connection.execute(
                """
                UPDATE knowledge_versions
                SET tenant_id = ?, access_scope = ?, allowed_groups_json = ?
                WHERE knowledge_id = ?
                  AND content_fingerprint = ?
                  AND normalization_strategy_version = ?
                """,
                (
                    access_policy.tenant_id,
                    access_policy.scope.value,
                    groups,
                    knowledge_id,
                    expected_state.content_fingerprint,
                    expected_state.normalization_strategy_version,
                ),
            )
            if version_cursor.rowcount != 1:
                raise RuntimeError("current knowledge version is missing")

            connection.execute(
                """
                UPDATE knowledge_chunks
                SET tenant_id = ?, access_scope = ?, allowed_groups_json = ?
                WHERE knowledge_id = ?
                  AND normalized_content_fingerprint = ?
                  AND normalization_strategy_version = ?
                """,
                (
                    access_policy.tenant_id,
                    access_policy.scope.value,
                    groups,
                    knowledge_id,
                    expected_state.content_fingerprint,
                    expected_state.normalization_strategy_version,
                ),
            )
            connection.execute(
                """
                UPDATE knowledge_state
                SET access_fingerprint = ?
                WHERE knowledge_id = ?
                """,
                (new_access_fingerprint, knowledge_id),
            )

        return CanonicalKnowledgeState(
            content_fingerprint=expected_state.content_fingerprint,
            normalization_strategy_version=expected_state.normalization_strategy_version,
            access_fingerprint=new_access_fingerprint,
        )

    def create_version(
        self,
        *,
        document: KnowledgeDocument,
        chunks: tuple[KnowledgeChunk, ...],
        state: CanonicalKnowledgeState,
        expected_previous: CanonicalKnowledgeState | None,
    ) -> None:
        if state.content_fingerprint != document.normalized_content_fingerprint:
            raise ValueError("state content fingerprint must match document")
        if state.normalization_strategy_version != document.normalization_strategy_version:
            raise ValueError("state normalization strategy must match document")
        expected_access = access_policy_fingerprint(document.access_policy)
        if state.access_fingerprint != expected_access:
            raise ValueError("state access fingerprint must match document")

        policy = document.access_policy
        groups = json.dumps(policy.allowed_groups, separators=(",", ":"))

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load_state(connection, document.knowledge_id)
            if current != expected_previous:
                raise ConcurrentKnowledgeUpdateError(
                    f"canonical state changed before version commit: {document.knowledge_id}"
                )

            connection.execute(
                """
                INSERT INTO knowledge_versions (
                    knowledge_id,
                    content_fingerprint,
                    normalization_strategy_version,
                    source_system,
                    source_record_id,
                    source_version,
                    content_type,
                    title,
                    content,
                    tenant_id,
                    access_scope,
                    allowed_groups_json,
                    raw_payload_fingerprint,
                    ingestion_fingerprint,
                    captured_at,
                    source_uri,
                    source_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.knowledge_id,
                    document.normalized_content_fingerprint,
                    document.normalization_strategy_version,
                    document.source_system,
                    document.source_record_id,
                    document.source_version,
                    document.content_type,
                    document.title,
                    document.content,
                    policy.tenant_id,
                    policy.scope.value,
                    groups,
                    document.raw_payload_fingerprint,
                    document.ingestion_fingerprint,
                    document.captured_at.isoformat(),
                    document.source_uri,
                    document.source_updated_at.isoformat()
                    if document.source_updated_at is not None
                    else None,
                ),
            )

            connection.executemany(
                """
                INSERT INTO knowledge_chunks (
                    chunk_id,
                    knowledge_id,
                    source_system,
                    source_record_id,
                    source_version,
                    document_title,
                    sequence_number,
                    text,
                    start_offset,
                    end_offset,
                    content_fingerprint,
                    ingestion_fingerprint,
                    normalized_content_fingerprint,
                    normalization_strategy_version,
                    tenant_id,
                    access_scope,
                    allowed_groups_json,
                    chunking_strategy_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.knowledge_id,
                        chunk.source_system,
                        chunk.source_record_id,
                        chunk.source_version,
                        chunk.document_title,
                        chunk.sequence_number,
                        chunk.text,
                        chunk.start_offset,
                        chunk.end_offset,
                        chunk.content_fingerprint,
                        chunk.ingestion_fingerprint,
                        chunk.normalized_content_fingerprint,
                        chunk.normalization_strategy_version,
                        chunk.access_policy.tenant_id,
                        chunk.access_policy.scope.value,
                        json.dumps(chunk.access_policy.allowed_groups, separators=(",", ":")),
                        chunk.strategy_version,
                    )
                    for chunk in chunks
                ],
            )

            connection.execute(
                """
                INSERT INTO knowledge_state (
                    knowledge_id,
                    content_fingerprint,
                    normalization_strategy_version,
                    access_fingerprint
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(knowledge_id) DO UPDATE SET
                    content_fingerprint = excluded.content_fingerprint,
                    normalization_strategy_version = excluded.normalization_strategy_version,
                    access_fingerprint = excluded.access_fingerprint
                """,
                (
                    document.knowledge_id,
                    state.content_fingerprint,
                    state.normalization_strategy_version,
                    state.access_fingerprint,
                ),
            )

    def find_completed(
        self,
        *,
        knowledge_id: str,
        ingestion_fingerprint: str,
    ) -> IngestionResult | None:
        with self._connect() as connection:
            row = cast(
                tuple[str, str, str, str, str, str, str, int, int] | None,
                connection.execute(
                    """
                    SELECT
                        run_id,
                        outcome,
                        version_action,
                        version_reason,
                        canonical_content_fingerprint,
                        knowledge_id,
                        ingestion_fingerprint,
                        chunks_written,
                        governance_refreshed
                    FROM ingestion_runs
                    WHERE knowledge_id = ?
                      AND ingestion_fingerprint = ?
                      AND status = 'COMPLETED'
                    """,
                    (knowledge_id, ingestion_fingerprint),
                ).fetchone(),
            )

        if row is None:
            return None

        return IngestionResult(
            run_id=row[0],
            knowledge_id=row[5],
            ingestion_fingerprint=row[6],
            outcome=IngestionOutcome(row[1]),
            action=VersionAction(row[2]),
            reason=VersionReason(row[3]),
            canonical_content_fingerprint=row[4],
            chunks_written=row[7],
            governance_refreshed=bool(row[8]),
        )

    def start(
        self,
        *,
        run_id: str,
        knowledge_id: str,
        ingestion_fingerprint: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO ingestion_runs (
                        run_id,
                        knowledge_id,
                        ingestion_fingerprint,
                        status,
                        stage,
                        started_at
                    ) VALUES (?, ?, ?, 'RUNNING', ?, ?)
                    """,
                    (
                        run_id,
                        knowledge_id,
                        ingestion_fingerprint,
                        IngestionStage.RECEIVED.value,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise IngestionAlreadyInProgressError(
                f"ingestion already exists for {knowledge_id}: {ingestion_fingerprint}"
            ) from exc

    def set_stage(self, run_id: str, stage: IngestionStage) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ingestion_runs
                SET stage = ?
                WHERE run_id = ? AND status = 'RUNNING'
                """,
                (stage.value, run_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"active ingestion run not found: {run_id}")

    def complete(self, result: IngestionResult) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ingestion_runs
                SET
                    status = 'COMPLETED',
                    stage = ?,
                    outcome = ?,
                    version_action = ?,
                    version_reason = ?,
                    canonical_content_fingerprint = ?,
                    chunks_written = ?,
                    governance_refreshed = ?,
                    completed_at = ?
                WHERE run_id = ? AND status = 'RUNNING'
                """,
                (
                    IngestionStage.COMPLETED.value,
                    result.outcome.value,
                    result.action.value,
                    result.reason.value,
                    result.canonical_content_fingerprint,
                    result.chunks_written,
                    int(result.governance_refreshed),
                    datetime.now(UTC).isoformat(),
                    result.run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"active ingestion run not found: {result.run_id}")

    def fail(
        self,
        *,
        run_id: str,
        stage: IngestionStage,
        error_type: str,
        error_message: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ingestion_runs
                SET
                    status = 'FAILED',
                    stage = ?,
                    error_type = ?,
                    error_message = ?,
                    completed_at = ?
                WHERE run_id = ? AND status = 'RUNNING'
                """,
                (
                    IngestionStage.FAILED.value,
                    error_type,
                    f"{stage.value}: {error_message}",
                    datetime.now(UTC).isoformat(),
                    run_id,
                ),
            )

    def _load_state(
        self,
        connection: sqlite3.Connection,
        knowledge_id: str,
    ) -> CanonicalKnowledgeState | None:
        row = cast(
            tuple[str, str, str] | None,
            connection.execute(
                """
                SELECT
                    content_fingerprint,
                    normalization_strategy_version,
                    access_fingerprint
                FROM knowledge_state
                WHERE knowledge_id = ?
                """,
                (knowledge_id,),
            ).fetchone(),
        )
        if row is None:
            return None
        return CanonicalKnowledgeState(
            content_fingerprint=row[0],
            normalization_strategy_version=row[1],
            access_fingerprint=row[2],
        )
