from dataclasses import replace
from datetime import UTC, datetime

import pytest

from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge import KnowledgeDocument, RetrievedKnowledge


def build_document(
    *,
    access_policy: AccessPolicy | None = None,
) -> KnowledgeDocument:
    return KnowledgeDocument(
        knowledge_id="KNOW-001",
        source_system="knowledge-base",
        source_record_id="ARTICLE-001",
        source_version="1",
        content_type="text/markdown",
        title="Reset an expired credential",
        content="Steps for regenerating and validating an expired credential.",
        access_policy=access_policy
        or AccessPolicy(
            tenant_id="acme",
            scope=AccessScope.TENANT,
        ),
        raw_payload_fingerprint="a" * 64,
        ingestion_fingerprint="b" * 64,
        normalized_content_fingerprint="c" * 64,
        normalization_strategy_version="canonical-text-v1",
        captured_at=datetime(2026, 9, 19, 10, 0, tzinfo=UTC),
        source_uri="https://knowledge.example/articles/ARTICLE-001",
        source_updated_at=datetime(2026, 9, 18, 9, 0, tzinfo=UTC),
    )


def test_accepts_document_with_three_identity_layers() -> None:
    document = build_document()

    assert document.raw_payload_fingerprint == "a" * 64
    assert document.ingestion_fingerprint == "b" * 64
    assert document.normalized_content_fingerprint == "c" * 64
    assert document.normalization_strategy_version == "canonical-text-v1"


def test_rejects_content_without_a_source_version() -> None:
    with pytest.raises(ValueError, match="source_version must not be blank"):
        replace(build_document(), source_version=" ")


def test_rejects_unresolved_access() -> None:
    unresolved_policy = AccessPolicy(
        tenant_id="acme",
        scope=AccessScope.UNRESOLVED,
    )

    with pytest.raises(
        ValueError,
        match="access_policy must be resolved",
    ):
        build_document(access_policy=unresolved_policy)


def test_rejects_invalid_raw_payload_fingerprint() -> None:
    with pytest.raises(ValueError, match="raw_payload_fingerprint"):
        replace(build_document(), raw_payload_fingerprint="not-a-sha256-digest")


def test_rejects_invalid_ingestion_fingerprint() -> None:
    with pytest.raises(ValueError, match="ingestion_fingerprint"):
        replace(build_document(), ingestion_fingerprint="not-a-sha256-digest")


def test_rejects_invalid_normalized_content_fingerprint() -> None:
    with pytest.raises(ValueError, match="normalized_content_fingerprint"):
        replace(build_document(), normalized_content_fingerprint="not-a-sha256-digest")


def test_rejects_a_capture_timestamp_without_timezone() -> None:
    with pytest.raises(
        ValueError,
        match="captured_at must include timezone information",
    ):
        replace(
            build_document(),
            captured_at=datetime(2026, 9, 19, 10, 0),
        )


def test_rejects_a_source_update_timestamp_without_timezone() -> None:
    with pytest.raises(
        ValueError,
        match="source_updated_at must include timezone information",
    ):
        replace(
            build_document(),
            source_updated_at=datetime(2026, 9, 18, 9, 0),
        )


def test_rejects_a_blank_source_uri_when_provided() -> None:
    with pytest.raises(
        ValueError,
        match="source_uri must not be blank when provided",
    ):
        replace(build_document(), source_uri=" ")


def test_rejects_a_blank_title() -> None:
    with pytest.raises(ValueError, match="title must not be blank"):
        replace(build_document(), title=" ")


def test_rejects_a_retrieval_score_outside_the_normalized_range() -> None:
    with pytest.raises(ValueError, match="score must be between"):
        RetrievedKnowledge(
            document=build_document(),
            score=1.01,
        )
