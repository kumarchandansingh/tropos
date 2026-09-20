from dataclasses import replace
from datetime import UTC, datetime

import pytest

from tropos.core.adapters.chunking.deterministic import DeterministicKnowledgeChunker
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge import KnowledgeDocument
from tropos.core.domain.knowledge_chunk import validate_chunk_set


def build_document(content: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        knowledge_id="KNOW-001",
        source_system="knowledge-base",
        source_record_id="ARTICLE-001",
        source_version="4",
        content_type="text/plain",
        title="Reset an expired credential",
        content=content,
        access_policy=AccessPolicy(
            tenant_id="acme",
            scope=AccessScope.TENANT,
        ),
        source_fingerprint="a" * 64,
        captured_at=datetime(2026, 9, 20, tzinfo=UTC),
    )


def test_short_document_remains_one_exact_chunk() -> None:
    document = build_document("Problem: Credential expired.\n\nResolution: Rotate it.")
    chunks = DeterministicKnowledgeChunker(max_characters=80).chunk(document)

    assert len(chunks) == 1
    assert chunks[0].text == document.content
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == len(document.content)


def test_long_document_prefers_paragraph_boundary() -> None:
    content = ("A" * 35) + "\n\n" + ("B" * 35) + "\n\n" + ("C" * 35)
    document = build_document(content)
    chunks = DeterministicKnowledgeChunker(max_characters=80).chunk(document)

    assert len(chunks) == 2
    assert chunks[0].text.endswith("\n\n")
    assert "".join(chunk.text for chunk in chunks) == content


def test_unbroken_text_uses_lossless_hard_boundaries() -> None:
    content = "X" * 95
    chunks = DeterministicKnowledgeChunker(max_characters=32).chunk(build_document(content))

    assert [len(chunk.text) for chunk in chunks] == [32, 32, 31]
    assert "".join(chunk.text for chunk in chunks) == content


def test_repeated_run_produces_same_chunk_ids() -> None:
    document = build_document("Paragraph one.\n\nParagraph two.\n\nParagraph three.")
    chunker = DeterministicKnowledgeChunker(max_characters=32)

    first = chunker.chunk(document)
    second = chunker.chunk(document)

    assert tuple(chunk.chunk_id for chunk in first) == tuple(chunk.chunk_id for chunk in second)


def test_chunks_inherit_document_access_and_provenance() -> None:
    document = build_document("A sufficiently useful piece of source knowledge.")
    chunk = DeterministicKnowledgeChunker(max_characters=80).chunk(document)[0]

    assert chunk.access_policy == document.access_policy
    assert chunk.source_fingerprint == document.source_fingerprint
    assert chunk.source_record_id == document.source_record_id
    assert chunk.document_title == document.title


def test_collection_validation_detects_an_omitted_chunk() -> None:
    document = build_document("X" * 95)
    chunks = DeterministicKnowledgeChunker(max_characters=32).chunk(document)

    with pytest.raises(ValueError, match="sequence must be contiguous"):
        validate_chunk_set(document=document, chunks=(chunks[0], chunks[2]))


def test_collection_validation_detects_source_text_tampering() -> None:
    document = build_document("This is the authoritative source text.")
    chunks = DeterministicKnowledgeChunker(max_characters=80).chunk(document)

    with pytest.raises(ValueError, match="exact source range"):
        validate_chunk_set(
            document=replace(
                document,
                content="X" + document.content[1:],
            ),
            chunks=chunks,
        )


def test_chunk_validation_detects_text_tampering() -> None:
    document = build_document("This is the authoritative source text.")
    chunk = DeterministicKnowledgeChunker(max_characters=80).chunk(document)[0]

    with pytest.raises(ValueError, match="content_fingerprint"):
        replace(chunk, text="X" + chunk.text[1:])


def test_strategy_version_changes_chunk_identity() -> None:
    document = build_document("One stable piece of source content.")
    first = DeterministicKnowledgeChunker(
        max_characters=80,
        strategy_version="structural-character-v1",
    ).chunk(document)[0]
    second = DeterministicKnowledgeChunker(
        max_characters=80,
        strategy_version="structural-character-v2",
    ).chunk(document)[0]

    assert first.chunk_id != second.chunk_id
