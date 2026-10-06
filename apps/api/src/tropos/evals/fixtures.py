"""Composition for isolated synthetic fixtures using the real ingestion and BM25 adapters."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

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
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge_chunk import KnowledgeChunk
from tropos.evals.catalogue import Catalogue, PlannedCase
from tropos.evals.execution import EvaluationContext


def prepare_fixture(catalogue: Catalogue, case: PlannedCase, directory: Path) -> EvaluationContext:
    database = directory / f"{uuid4().hex}.sqlite"
    store = SQLiteIngestionStore(database)
    ingestion = IngestKnowledge(
        parser=DeterministicKnowledgeParser(),
        normalizer=DeterministicKnowledgeNormalizer(),
        chunker=DeterministicKnowledgeChunker(max_characters=2000),
        source_captures=store,
        knowledge_repository=store,
        runs=store,
    )
    for document in (*catalogue.documents, *case.updates):
        raw = RawKnowledgeRecord(
            source_system=f"eval:{catalogue.dataset_id}",
            source_record_id=document.knowledge_id + ".md",
            source_version=document.source_version,
            content_type="text/markdown",
            payload=document.text.encode(),
            access_policy=document.access,
            captured_at=datetime(2026, 9, 26, tzinfo=UTC),
        )
        ingestion.execute(IngestKnowledgeCommand(document.knowledge_id, raw))
    chunks: dict[str, KnowledgeChunk] = {}
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("""SELECT c.* FROM knowledge_chunks c
            JOIN knowledge_state s ON c.knowledge_id=s.knowledge_id
            WHERE c.normalized_content_fingerprint=s.content_fingerprint
            AND c.normalization_strategy_version=s.normalization_strategy_version""").fetchall()
        for row in rows:
            chunk = KnowledgeChunk(
                chunk_id=row["chunk_id"],
                knowledge_id=row["knowledge_id"],
                source_system=row["source_system"],
                source_record_id=row["source_record_id"],
                source_version=row["source_version"],
                document_title=row["document_title"],
                sequence_number=row["sequence_number"],
                text=row["text"],
                start_offset=row["start_offset"],
                end_offset=row["end_offset"],
                content_fingerprint=row["content_fingerprint"],
                ingestion_fingerprint=row["ingestion_fingerprint"],
                normalized_content_fingerprint=row["normalized_content_fingerprint"],
                normalization_strategy_version=row["normalization_strategy_version"],
                access_policy=AccessPolicy(
                    row["tenant_id"],
                    AccessScope(row["access_scope"]),
                    tuple(json.loads(row["allowed_groups_json"])),
                ),
                strategy_version=row["chunking_strategy_version"],
            )
            chunks[chunk.chunk_id] = chunk
    finally:
        connection.close()
    return EvaluationContext(SQLiteFtsKnowledgeRetriever(database), chunks)
