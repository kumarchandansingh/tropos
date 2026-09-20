from datetime import UTC, datetime

import pytest

from tropos.core.adapters.normalization.deterministic import DeterministicKnowledgeNormalizer
from tropos.core.application.ingestion.normalization import (
    ExtractedKnowledgeText,
    TextFormat,
    materialize_knowledge_document,
)
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.domain.access import AccessPolicy, AccessScope


def build_source(
    text: str,
    *,
    title: str = "Credential reset",
    text_format: TextFormat = TextFormat.MARKDOWN,
) -> ExtractedKnowledgeText:
    raw = RawKnowledgeRecord(
        source_system="test-knowledge-base",
        source_record_id="ARTICLE-001",
        source_version="7",
        content_type="text/markdown",
        payload=text.encode("utf-8"),
        access_policy=AccessPolicy(
            tenant_id="acme",
            scope=AccessScope.TENANT,
        ),
        captured_at=datetime(2026, 9, 21, tzinfo=UTC),
    )
    return ExtractedKnowledgeText(
        raw_record=raw,
        title=title,
        text=text,
        text_format=text_format,
    )


def test_formatting_only_changes_share_canonical_fingerprint() -> None:
    first = build_source("\ufeff# Reset\r\n\r\nUse the portal.   \r\n\r\n\r\n- Verify login\r\n")
    second = build_source("# Reset\n\nUse the portal.\n\n* Verify login")

    normalizer = DeterministicKnowledgeNormalizer()

    normalized_first = normalizer.normalize(first)
    normalized_second = normalizer.normalize(second)

    assert normalized_first.content_fingerprint == normalized_second.content_fingerprint
    assert normalized_first.canonical_text == normalized_second.canonical_text


def test_unicode_canonical_equivalents_share_fingerprint() -> None:
    composed = build_source("# Café\n\nReset access.")
    decomposed = build_source("# Cafe\u0301\n\nReset access.")

    normalizer = DeterministicKnowledgeNormalizer()

    assert (
        normalizer.normalize(composed).content_fingerprint
        == normalizer.normalize(decomposed).content_fingerprint
    )


def test_meaningful_content_change_changes_fingerprint() -> None:
    old = build_source("# Password policy\n\nPasswords expire after 90 days.")
    new = build_source("# Password policy\n\nPasswords expire after 60 days.")

    normalizer = DeterministicKnowledgeNormalizer()

    assert (
        normalizer.normalize(old).content_fingerprint
        != normalizer.normalize(new).content_fingerprint
    )


def test_heading_level_is_preserved_as_meaningful_structure() -> None:
    first = build_source("# Reset\n\nUse the portal.")
    second = build_source("## Reset\n\nUse the portal.")

    normalizer = DeterministicKnowledgeNormalizer()

    assert (
        normalizer.normalize(first).content_fingerprint
        != normalizer.normalize(second).content_fingerprint
    )


def test_repeated_run_is_deterministic() -> None:
    source = build_source("# Reset\n\n1. Open settings\n2. Rotate credential")
    normalizer = DeterministicKnowledgeNormalizer()

    first = normalizer.normalize(source)
    second = normalizer.normalize(source)

    assert first == second


def test_normalization_rejects_content_that_becomes_empty() -> None:
    raw = RawKnowledgeRecord(
        source_system="test-knowledge-base",
        source_record_id="ARTICLE-001",
        source_version="1",
        content_type="text/plain",
        payload="\ufeff\r\n".encode("utf-8"),
        access_policy=AccessPolicy(
            tenant_id="acme",
            scope=AccessScope.TENANT,
        ),
        captured_at=datetime(2026, 9, 21, tzinfo=UTC),
    )
    source = ExtractedKnowledgeText(
        raw_record=raw,
        title="Title",
        text="\ufeff\r\n",
        text_format=TextFormat.PLAIN,
    )

    with pytest.raises(ValueError, match="normalization produced empty text"):
        DeterministicKnowledgeNormalizer().normalize(source)


def test_materialization_preserves_raw_and_normalized_identity_layers() -> None:
    source = build_source("# Reset\n\nUse the portal.")
    normalized = DeterministicKnowledgeNormalizer().normalize(source)

    document = materialize_knowledge_document(
        knowledge_id="KNOW-001",
        normalized=normalized,
    )

    assert document.raw_payload_fingerprint == source.raw_record.raw_payload_fingerprint
    assert document.ingestion_fingerprint == source.raw_record.ingestion_fingerprint
    assert document.normalized_content_fingerprint == normalized.content_fingerprint
    assert document.content == normalized.canonical_text
