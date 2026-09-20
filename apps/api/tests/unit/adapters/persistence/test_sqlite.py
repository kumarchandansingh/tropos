import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from tropos.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.adapters.persistence.sqlite import SQLiteKnowledgeCorpusStore
from tropos.domain.access import AccessPolicy, AccessScope
from tropos.domain.knowledge import KnowledgeDocument


def build_document(
    *,
    knowledge_id: str = "KNOW-001",
    source_version: str = "1",
    content: str = "Problem: credential expired.\n\nResolution: rotate the credential.",
    fingerprint: str = "a" * 64,
) -> KnowledgeDocument:
    return KnowledgeDocument(
        knowledge_id=knowledge_id,
        source_system="knowledge-base",
        source_record_id=f"ARTICLE-{knowledge_id}",
        source_version=source_version,
        content_type="text/plain",
        title="Reset an expired credential",
        content=content,
        access_policy=AccessPolicy(
            tenant_id="acme",
            scope=AccessScope.RESTRICTED,
            allowed_groups=("support", "tier-2"),
        ),
        source_fingerprint=fingerprint,
        captured_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        source_uri="https://knowledge.example/article",
        source_updated_at=datetime(2026, 9, 20, 11, 30, tzinfo=UTC),
    )


def build_store(connection: sqlite3.Connection) -> SQLiteKnowledgeCorpusStore:
    store = SQLiteKnowledgeCorpusStore(connection)
    store.initialize_schema()
    return store


def test_round_trip_preserves_document_chunks_access_and_provenance() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        store = build_store(connection)
        document = build_document()
        chunks = DeterministicKnowledgeChunker(max_characters=40).chunk(document)

        store.save(document, chunks)

        assert store.get_document(document.knowledge_id) == document
        assert store.get_chunks(document.knowledge_id) == chunks
    finally:
        connection.close()


def test_saving_new_snapshot_replaces_old_chunks_atomically() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        store = build_store(connection)
        original = build_document(content="A" * 90)
        original_chunks = DeterministicKnowledgeChunker(max_characters=32).chunk(original)
        store.save(original, original_chunks)

        updated = build_document(
            source_version="2",
            content="B" * 70,
            fingerprint="b" * 64,
        )
        updated_chunks = DeterministicKnowledgeChunker(max_characters=32).chunk(updated)
        store.save(updated, updated_chunks)

        assert store.get_document(updated.knowledge_id) == updated
        assert store.get_chunks(updated.knowledge_id) == updated_chunks
        assert not set(chunk.chunk_id for chunk in original_chunks) & set(
            chunk.chunk_id for chunk in store.get_chunks(updated.knowledge_id)
        )
    finally:
        connection.close()


def test_multiple_knowledge_items_remain_isolated() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        store = build_store(connection)
        first = build_document(knowledge_id="KNOW-001")
        second = build_document(
            knowledge_id="KNOW-002",
            content="A different governed knowledge article.",
            fingerprint="c" * 64,
        )

        first_chunks = DeterministicKnowledgeChunker(max_characters=80).chunk(first)
        second_chunks = DeterministicKnowledgeChunker(max_characters=80).chunk(second)
        store.save(first, first_chunks)
        store.save(second, second_chunks)

        assert store.get_document("KNOW-001") == first
        assert store.get_chunks("KNOW-001") == first_chunks
        assert store.get_document("KNOW-002") == second
        assert store.get_chunks("KNOW-002") == second_chunks
    finally:
        connection.close()


def test_missing_identity_returns_empty_persistence_result() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        store = build_store(connection)

        assert store.get_document("UNKNOWN") is None
        assert store.get_chunks("UNKNOWN") == ()
    finally:
        connection.close()


def test_save_revalidates_chunk_set_before_persisting() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        store = build_store(connection)
        document = build_document(content="X" * 70)
        chunks = DeterministicKnowledgeChunker(max_characters=32).chunk(document)
        invalid_chunks = (chunks[0], replace(chunks[1], sequence_number=3), chunks[2])

        with pytest.raises(ValueError, match="sequence must be contiguous"):
            store.save(document, invalid_chunks)

        assert store.get_document(document.knowledge_id) is None
        assert store.get_chunks(document.knowledge_id) == ()
    finally:
        connection.close()


def test_blank_identity_is_rejected_before_query() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        store = build_store(connection)

        with pytest.raises(ValueError, match="knowledge_id must not be blank"):
            store.get_document("   ")

        with pytest.raises(ValueError, match="knowledge_id must not be blank"):
            store.get_chunks("")
    finally:
        connection.close()
