import json
import re
import sqlite3
from pathlib import Path
from typing import cast

from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievedKnowledgeChunk,
)
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge_chunk import KnowledgeChunk

_STRATEGY_VERSION = "sqlite-fts5-bm25-v1"
_TOKEN_PATTERN = re.compile(r"[\w-]+", flags=re.UNICODE)


class RetrievalBackendUnavailableError(RuntimeError):
    """Raised when the configured SQLite database cannot support retrieval."""


class SQLiteFtsKnowledgeRetriever:
    """Governed lexical retrieval over current canonical chunks using SQLite FTS5."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)
        self._initialize()

    @property
    def strategy_version(self) -> str:
        return _STRATEGY_VERSION

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            required_tables = {"knowledge_chunks", "knowledge_state"}
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            existing_tables = {str(row["name"]) for row in rows}
            missing = required_tables - existing_tables
            if missing:
                missing_names = ", ".join(sorted(missing))
                raise RetrievalBackendUnavailableError(
                    f"retrieval requires initialized ingestion tables: {missing_names}"
                )

            fts_exists = "knowledge_chunks_fts" in existing_tables
            try:
                connection.executescript(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
                        document_title,
                        text,
                        content='knowledge_chunks',
                        content_rowid='rowid',
                        tokenize='unicode61'
                    );

                    CREATE TRIGGER IF NOT EXISTS knowledge_chunks_fts_after_insert
                    AFTER INSERT ON knowledge_chunks BEGIN
                        INSERT INTO knowledge_chunks_fts(rowid, document_title, text)
                        VALUES (new.rowid, new.document_title, new.text);
                    END;

                    CREATE TRIGGER IF NOT EXISTS knowledge_chunks_fts_after_delete
                    AFTER DELETE ON knowledge_chunks BEGIN
                        INSERT INTO knowledge_chunks_fts(
                            knowledge_chunks_fts,
                            rowid,
                            document_title,
                            text
                        ) VALUES ('delete', old.rowid, old.document_title, old.text);
                    END;

                    CREATE TRIGGER IF NOT EXISTS knowledge_chunks_fts_after_text_update
                    AFTER UPDATE OF document_title, text ON knowledge_chunks BEGIN
                        INSERT INTO knowledge_chunks_fts(
                            knowledge_chunks_fts,
                            rowid,
                            document_title,
                            text
                        ) VALUES ('delete', old.rowid, old.document_title, old.text);
                        INSERT INTO knowledge_chunks_fts(rowid, document_title, text)
                        VALUES (new.rowid, new.document_title, new.text);
                    END;
                    """
                )
                if not fts_exists:
                    connection.execute(
                        "INSERT INTO knowledge_chunks_fts(knowledge_chunks_fts) VALUES ('rebuild')"
                    )
            except sqlite3.OperationalError as exc:
                raise RetrievalBackendUnavailableError(
                    "SQLite retrieval requires an FTS5-enabled SQLite build"
                ) from exc

    def search(self, request: KnowledgeSearchRequest) -> tuple[RetrievedKnowledgeChunk, ...]:
        if not isinstance(request, KnowledgeSearchRequest):
            raise TypeError("request must be a KnowledgeSearchRequest")

        match_query = self._match_query(request.query)
        if match_query is None:
            return ()

        groups = request.access.groups
        params: list[str | int] = [match_query, request.access.tenant_id]

        if groups:
            group_placeholders = ", ".join("?" for _ in groups)
            access_clause = f"""
                (
                    c.access_scope = 'tenant'
                    OR (
                        c.access_scope = 'restricted'
                        AND EXISTS (
                            SELECT 1
                            FROM json_each(c.allowed_groups_json) AS allowed_group
                            WHERE allowed_group.value IN ({group_placeholders})
                        )
                    )
                )
            """
            params.extend(groups)
        else:
            access_clause = "c.access_scope = 'tenant'"

        params.append(request.limit)
        with self._connect() as connection:
            try:
                rows = connection.execute(
                    f"""
                    SELECT
                        c.chunk_id,
                        c.knowledge_id,
                        c.source_system,
                        c.source_record_id,
                        c.source_version,
                        c.document_title,
                        c.sequence_number,
                        c.text,
                        c.start_offset,
                        c.end_offset,
                        c.content_fingerprint,
                        c.ingestion_fingerprint,
                        c.normalized_content_fingerprint,
                        c.normalization_strategy_version,
                        c.tenant_id,
                        c.access_scope,
                        c.allowed_groups_json,
                        c.chunking_strategy_version,
                        -bm25(knowledge_chunks_fts, 3.0, 1.0) AS retrieval_score
                    FROM knowledge_chunks_fts
                    JOIN knowledge_chunks AS c
                      ON c.rowid = knowledge_chunks_fts.rowid
                    JOIN knowledge_state AS state
                      ON state.knowledge_id = c.knowledge_id
                    WHERE knowledge_chunks_fts MATCH ?
                      AND c.tenant_id = ?
                      AND c.normalized_content_fingerprint = state.content_fingerprint
                      AND c.normalization_strategy_version = state.normalization_strategy_version
                      AND {access_clause}
                    ORDER BY
                        bm25(knowledge_chunks_fts, 3.0, 1.0) ASC,
                        c.knowledge_id ASC,
                        c.sequence_number ASC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
            except sqlite3.OperationalError as exc:
                raise RetrievalBackendUnavailableError("SQLite lexical retrieval failed") from exc

        results: list[RetrievedKnowledgeChunk] = []
        for rank, row in enumerate(rows, start=1):
            allowed_groups = tuple(cast(list[str], json.loads(str(row["allowed_groups_json"]))))
            access_policy = AccessPolicy(
                tenant_id=str(row["tenant_id"]),
                scope=AccessScope(str(row["access_scope"])),
                allowed_groups=allowed_groups,
            )
            chunk = KnowledgeChunk(
                chunk_id=str(row["chunk_id"]),
                knowledge_id=str(row["knowledge_id"]),
                source_system=str(row["source_system"]),
                source_record_id=str(row["source_record_id"]),
                source_version=str(row["source_version"]),
                document_title=str(row["document_title"]),
                sequence_number=int(row["sequence_number"]),
                text=str(row["text"]),
                start_offset=int(row["start_offset"]),
                end_offset=int(row["end_offset"]),
                content_fingerprint=str(row["content_fingerprint"]),
                ingestion_fingerprint=str(row["ingestion_fingerprint"]),
                normalized_content_fingerprint=str(row["normalized_content_fingerprint"]),
                normalization_strategy_version=str(row["normalization_strategy_version"]),
                access_policy=access_policy,
                strategy_version=str(row["chunking_strategy_version"]),
            )
            results.append(
                RetrievedKnowledgeChunk(
                    chunk=chunk,
                    rank=rank,
                    score=float(row["retrieval_score"]),
                    strategy_version=self.strategy_version,
                )
            )

        return tuple(results)

    @staticmethod
    def _match_query(query: str) -> str | None:
        terms = tuple(dict.fromkeys(term.casefold() for term in _TOKEN_PATTERN.findall(query)))
        if not terms:
            return None
        return " OR ".join(f'"{term}"' for term in terms)
