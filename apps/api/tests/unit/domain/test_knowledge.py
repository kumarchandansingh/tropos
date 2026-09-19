import pytest

from tropos.domain.knowledge import KnowledgeDocument, RetrievedKnowledge


def build_document() -> KnowledgeDocument:
    return KnowledgeDocument(
        knowledge_id="KNOW-001",
        source_system="knowledge-base",
        source_record_id="ARTICLE-001",
        version="1",
        title="Reset an expired credential",
        content="Steps for regenerating and validating an expired credential.",
    )


def test_accepts_a_document_with_source_provenance() -> None:
    document = build_document()

    assert document.source_record_id == "ARTICLE-001"


def test_rejects_content_without_a_version() -> None:
    with pytest.raises(ValueError, match="version must not be blank"):
        KnowledgeDocument(
            knowledge_id="KNOW-001",
            source_system="knowledge-base",
            source_record_id="ARTICLE-001",
            version=" ",
            title="Credential reset",
            content="Reset the credential.",
        )


def test_rejects_a_retrieval_score_outside_the_normalized_range() -> None:
    with pytest.raises(ValueError, match="score must be between"):
        RetrievedKnowledge(
            document=build_document(),
            score=1.01,
        )
