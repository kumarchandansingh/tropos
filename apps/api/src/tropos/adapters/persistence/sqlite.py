import json
import sqlite3
from datetime import datetime
from typing import cast

from tropos.domain.access import AccessPolicy, AccessScope
from tropos.domain.knowledge import KnowledgeDocument
from tropos.domain.knowledge_chunk import KnowledgeChunk, validate_chunk_set

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_documents (
    knowledge_id TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_version TEXT NOT NULL,
    content_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    access_scope TEXT NOT NULL,
    allowed_groups_json TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    source_uri TEXT,
    source_updated_at TEXT
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
    source_fingerprint TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    access_scope TEXT NOT NULL,
    allowed_groups_json TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    FOREIGN KEY (knowledge_id) REFERENCES knowledge_documents(knowledge_id) ON DELETE CASCADE,
    UNIQUE (knowledge_id, sequence_number)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_source
ON knowledge_documents(source_system, source_record_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_knowledge
ON knowledge_chunks(knowledge_id, sequence_number);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_access
ON knowledge_chunks(tenant_id, access_scope);
"""

_DOCUMENT_COLUMNS = """
knowledge_id,
source_system,
source_record_id,
source_version,
content_type,
title,
content,
tenant_id,
access_scope,
allowed_groups_json,
source_fingerprint,
captured_at,
source_uri,
source_updated_at
"""

_CHUNK_COLUMNS = """
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
source_fingerprint,
tenant_id,
access_scope,
allowed_groups_json,
strategy_version
"""


class SQLiteKnowledgeCorpusStore:
    """SQLite baseline for the current canonical knowledge corpus."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

    def initialize_schema(self) -> None:
        """Create the current baseline schema if it does not yet exist."""

        self._connection.executescript(_SCHEMA)

    def save(
        self,
        document: KnowledgeDocument,
        chunks: tuple[KnowledgeChunk, ...],
    ) -> None:
        """Atomically replace the current persisted snapshot for one knowledge item."""

        validate_chunk_set(document=document, chunks=chunks)

        with self._connection:
            self._connection.execute(
                f"""
                INSERT INTO knowledge_documents ({_DOCUMENT_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(knowledge_id) DO UPDATE SET
                    source_system = excluded.source_system,
                    source_record_id = excluded.source_record_id,
                    source_version = excluded.source_version,
                    content_type = excluded.content_type,
                    title = excluded.title,
                    content = excluded.content,
                    tenant_id = excluded.tenant_id,
                    access_scope = excluded.access_scope,
                    allowed_groups_json = excluded.allowed_groups_json,
                    source_fingerprint = excluded.source_fingerprint,
                    captured_at = excluded.captured_at,
                    source_uri = excluded.source_uri,
                    source_updated_at = excluded.source_updated_at
                """,
                _document_values(document),
            )
            self._connection.execute(
                "DELETE FROM knowledge_chunks WHERE knowledge_id = ?",
                (document.knowledge_id,),
            )
            self._connection.executemany(
                f"""
                INSERT INTO knowledge_chunks ({_CHUNK_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(_chunk_values(chunk) for chunk in chunks),
            )

    def get_document(self, knowledge_id: str) -> KnowledgeDocument | None:
        """Reload the current canonical document by stable knowledge identity."""

        normalized_id = knowledge_id.strip()
        if not normalized_id:
            raise ValueError("knowledge_id must not be blank")

        row = self._connection.execute(
            f"SELECT {_DOCUMENT_COLUMNS} FROM knowledge_documents WHERE knowledge_id = ?",
            (normalized_id,),
        ).fetchone()
        if row is None:
            return None

        return _document_from_row(row)

    def get_chunks(self, knowledge_id: str) -> tuple[KnowledgeChunk, ...]:
        """Reload persisted chunks in deterministic source order."""

        normalized_id = knowledge_id.strip()
        if not normalized_id:
            raise ValueError("knowledge_id must not be blank")

        rows = self._connection.execute(
            f"""
            SELECT {_CHUNK_COLUMNS}
            FROM knowledge_chunks
            WHERE knowledge_id = ?
            ORDER BY sequence_number
            """,
            (normalized_id,),
        ).fetchall()
        return tuple(_chunk_from_row(row) for row in rows)


def _document_values(document: KnowledgeDocument) -> tuple[object, ...]:
    return (
        document.knowledge_id,
        document.source_system,
        document.source_record_id,
        document.source_version,
        document.content_type,
        document.title,
        document.content,
        document.access_policy.tenant_id,
        document.access_policy.scope.value,
        _serialize_groups(document.access_policy.allowed_groups),
        document.source_fingerprint,
        document.captured_at.isoformat(),
        document.source_uri,
        document.source_updated_at.isoformat() if document.source_updated_at is not None else None,
    )


def _chunk_values(chunk: KnowledgeChunk) -> tuple[object, ...]:
    return (
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
        chunk.source_fingerprint,
        chunk.access_policy.tenant_id,
        chunk.access_policy.scope.value,
        _serialize_groups(chunk.access_policy.allowed_groups),
        chunk.strategy_version,
    )


def _document_from_row(row: sqlite3.Row) -> KnowledgeDocument:
    return KnowledgeDocument(
        knowledge_id=_row_str(row, "knowledge_id"),
        source_system=_row_str(row, "source_system"),
        source_record_id=_row_str(row, "source_record_id"),
        source_version=_row_str(row, "source_version"),
        content_type=_row_str(row, "content_type"),
        title=_row_str(row, "title"),
        content=_row_str(row, "content"),
        access_policy=_access_policy_from_row(row),
        source_fingerprint=_row_str(row, "source_fingerprint"),
        captured_at=datetime.fromisoformat(_row_str(row, "captured_at")),
        source_uri=_row_optional_str(row, "source_uri"),
        source_updated_at=_row_optional_datetime(row, "source_updated_at"),
    )


def _chunk_from_row(row: sqlite3.Row) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=_row_str(row, "chunk_id"),
        knowledge_id=_row_str(row, "knowledge_id"),
        source_system=_row_str(row, "source_system"),
        source_record_id=_row_str(row, "source_record_id"),
        source_version=_row_str(row, "source_version"),
        document_title=_row_str(row, "document_title"),
        sequence_number=_row_int(row, "sequence_number"),
        text=_row_str(row, "text"),
        start_offset=_row_int(row, "start_offset"),
        end_offset=_row_int(row, "end_offset"),
        content_fingerprint=_row_str(row, "content_fingerprint"),
        source_fingerprint=_row_str(row, "source_fingerprint"),
        access_policy=_access_policy_from_row(row),
        strategy_version=_row_str(row, "strategy_version"),
    )


def _access_policy_from_row(row: sqlite3.Row) -> AccessPolicy:
    return AccessPolicy(
        tenant_id=_row_str(row, "tenant_id"),
        scope=AccessScope(_row_str(row, "access_scope")),
        allowed_groups=_deserialize_groups(_row_str(row, "allowed_groups_json")),
    )


def _serialize_groups(groups: tuple[str, ...]) -> str:
    return json.dumps(groups, separators=(",", ":"))


def _deserialize_groups(value: str) -> tuple[str, ...]:
    raw = cast(object, json.loads(value))
    if not isinstance(raw, list):
        raise ValueError("allowed_groups_json must contain a JSON array")

    groups: list[str] = []
    for item in cast(list[object], raw):
        if not isinstance(item, str):
            raise ValueError("allowed_groups_json must contain only strings")
        groups.append(item)
    return tuple(groups)


def _row_str(row: sqlite3.Row, field_name: str) -> str:
    value = cast(object, row[field_name])
    if not isinstance(value, str):
        raise ValueError(f"persisted {field_name} must be text")
    return value


def _row_optional_str(row: sqlite3.Row, field_name: str) -> str | None:
    value = cast(object, row[field_name])
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"persisted {field_name} must be text when present")
    return value


def _row_int(row: sqlite3.Row, field_name: str) -> int:
    value = cast(object, row[field_name])
    if not isinstance(value, int):
        raise ValueError(f"persisted {field_name} must be an integer")
    return value


def _row_optional_datetime(row: sqlite3.Row, field_name: str) -> datetime | None:
    value = _row_optional_str(row, field_name)
    return datetime.fromisoformat(value) if value is not None else None
