import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import cast

from tropos.core.application.embeddings.models import (
    EmbeddedKnowledgeChunk,
    EmbeddingVector,
    KnowledgeEmbedding,
    SimilarityMetric,
)
from tropos.core.application.retrieval.models import RetrievalAccessContext
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge_chunk import KnowledgeChunk


class SQLiteEmbeddingRepository:
    """SQLite persistence for derived embeddings with governed candidate selection."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            tables = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            required = {"knowledge_chunks", "knowledge_state"}
            missing = required - tables
            if missing:
                missing_names = ", ".join(sorted(missing))
                raise RuntimeError(
                    f"embedding repository requires initialized ingestion tables: {missing_names}"
                )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                    chunk_id TEXT NOT NULL,
                    embedding_strategy_version TEXT NOT NULL,
                    model_identifier TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    similarity_metric TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (chunk_id, embedding_strategy_version)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_embeddings_strategy
                ON knowledge_embeddings (embedding_strategy_version, chunk_id)
                """
            )

    def missing_current_chunks(
        self,
        *,
        embedding_strategy_version: str,
        limit: int,
    ) -> tuple[KnowledgeChunk, ...]:
        if not embedding_strategy_version.strip():
            raise ValueError("embedding_strategy_version must not be blank")
        if limit < 1:
            raise ValueError("limit must be at least 1")

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.*
                FROM knowledge_chunks AS c
                JOIN knowledge_state AS state
                  ON state.knowledge_id = c.knowledge_id
                LEFT JOIN knowledge_embeddings AS e
                  ON e.chunk_id = c.chunk_id
                 AND e.embedding_strategy_version = ?
                WHERE state.lifecycle_status = 'ACTIVE'
                  AND c.normalized_content_fingerprint = state.content_fingerprint
                  AND c.normalization_strategy_version = state.normalization_strategy_version
                  AND e.chunk_id IS NULL
                ORDER BY c.knowledge_id ASC, c.sequence_number ASC
                LIMIT ?
                """,
                (embedding_strategy_version, limit),
            ).fetchall()

        return tuple(self._chunk_from_row(row) for row in rows)

    def upsert(self, embeddings: tuple[KnowledgeEmbedding, ...]) -> None:
        if not embeddings:
            return

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO knowledge_embeddings (
                    chunk_id,
                    embedding_strategy_version,
                    model_identifier,
                    dimensions,
                    similarity_metric,
                    vector_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id, embedding_strategy_version) DO UPDATE SET
                    model_identifier = excluded.model_identifier,
                    dimensions = excluded.dimensions,
                    similarity_metric = excluded.similarity_metric,
                    vector_json = excluded.vector_json,
                    created_at = excluded.created_at
                """,
                [
                    (
                        embedding.chunk_id,
                        embedding.embedding_strategy_version,
                        embedding.model_identifier,
                        embedding.vector.dimensions,
                        embedding.similarity_metric.value,
                        json.dumps(embedding.vector.values, separators=(",", ":")),
                        embedding.created_at.isoformat(),
                    )
                    for embedding in embeddings
                ],
            )

    def eligible_embeddings(
        self,
        *,
        access: RetrievalAccessContext,
        embedding_strategy_version: str,
    ) -> tuple[EmbeddedKnowledgeChunk, ...]:
        if not embedding_strategy_version.strip():
            raise ValueError("embedding_strategy_version must not be blank")

        params: list[str] = [embedding_strategy_version, access.tenant_id]
        if access.groups:
            placeholders = ", ".join("?" for _ in access.groups)
            access_clause = f"""
                (
                    c.access_scope = 'tenant'
                    OR (
                        c.access_scope = 'restricted'
                        AND EXISTS (
                            SELECT 1
                            FROM json_each(c.allowed_groups_json) AS allowed_group
                            WHERE allowed_group.value IN ({placeholders})
                        )
                    )
                )
            """
            params.extend(access.groups)
        else:
            access_clause = "c.access_scope = 'tenant'"

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    c.*,
                    e.embedding_strategy_version,
                    e.model_identifier,
                    e.dimensions,
                    e.similarity_metric,
                    e.vector_json,
                    e.created_at
                FROM knowledge_embeddings AS e
                JOIN knowledge_chunks AS c
                  ON c.chunk_id = e.chunk_id
                JOIN knowledge_state AS state
                  ON state.knowledge_id = c.knowledge_id
                WHERE e.embedding_strategy_version = ?
                  AND c.tenant_id = ?
                  AND state.lifecycle_status = 'ACTIVE'
                  AND c.normalized_content_fingerprint = state.content_fingerprint
                  AND c.normalization_strategy_version = state.normalization_strategy_version
                  AND {access_clause}
                ORDER BY c.knowledge_id ASC, c.sequence_number ASC
                """,
                tuple(params),
            ).fetchall()

        return tuple(self._embedded_from_row(row) for row in rows)

    @staticmethod
    def _chunk_from_row(row: sqlite3.Row) -> KnowledgeChunk:
        allowed_groups = tuple(cast(list[str], json.loads(str(row["allowed_groups_json"]))))
        return KnowledgeChunk(
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
            access_policy=AccessPolicy(
                tenant_id=str(row["tenant_id"]),
                scope=AccessScope(str(row["access_scope"])),
                allowed_groups=allowed_groups,
            ),
            strategy_version=str(row["chunking_strategy_version"]),
        )

    @classmethod
    def _embedded_from_row(cls, row: sqlite3.Row) -> EmbeddedKnowledgeChunk:
        chunk = cls._chunk_from_row(row)
        vector_values = tuple(float(value) for value in json.loads(str(row["vector_json"])))
        dimensions = int(row["dimensions"])
        if len(vector_values) != dimensions:
            raise RuntimeError("persisted embedding dimensions do not match vector payload")

        embedding = KnowledgeEmbedding(
            chunk_id=chunk.chunk_id,
            embedding_strategy_version=str(row["embedding_strategy_version"]),
            model_identifier=str(row["model_identifier"]),
            similarity_metric=SimilarityMetric(str(row["similarity_metric"])),
            vector=EmbeddingVector(vector_values),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )
        return EmbeddedKnowledgeChunk(chunk=chunk, embedding=embedding)
