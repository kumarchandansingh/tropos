"""Application-service tests for governed Knowledge Article generation."""

from hashlib import sha256

import pytest

from tropos.capabilities.resolve.application.generate_knowledge_article import (
    GenerateKnowledgeArticle,
    GenerateKnowledgeArticleCommand,
)
from tropos.capabilities.resolve.application.knowledge_article_request import (
    DetailLevel,
    KnowledgeArticleGenerationRequest,
    KnowledgeArticlePromptInputs,
    OutputPreferences,
    PromptProfileRef,
)
from tropos.capabilities.resolve.application.ports.knowledge_article import (
    KnowledgeArticleEvidenceExcerpt,
)
from tropos.core.application.retrieval.models import (
    KnowledgeSearchRequest,
    RetrievedKnowledgeChunk,
)
from tropos.core.domain.access import AccessPolicy, AccessScope
from tropos.core.domain.knowledge_article import (
    ArticleStep,
    ArticleType,
    EvidenceClaim,
    HowToArticle,
    KnowledgeArticleDraft,
)
from tropos.core.domain.knowledge_chunk import KnowledgeChunk, text_fingerprint


class FakeRetriever:
    strategy_version = "fake-retriever-v1"

    def __init__(self, results: tuple[RetrievedKnowledgeChunk, ...]) -> None:
        self.results = results
        self.request: KnowledgeSearchRequest | None = None

    def search(
        self,
        request: KnowledgeSearchRequest,
    ) -> tuple[RetrievedKnowledgeChunk, ...]:
        self.request = request
        return self.results


class RecordingGenerator:
    def __init__(self) -> None:
        self.prompt_inputs: KnowledgeArticlePromptInputs | None = None
        self.evidence: tuple[KnowledgeArticleEvidenceExcerpt, ...] | None = None

    def generate(
        self,
        prompt_inputs: KnowledgeArticlePromptInputs,
        evidence: tuple[KnowledgeArticleEvidenceExcerpt, ...],
    ) -> KnowledgeArticleDraft:
        self.prompt_inputs = prompt_inputs
        self.evidence = evidence
        reference = evidence[0].reference
        claim = EvidenceClaim("Reconnect the device.", (reference,))
        return KnowledgeArticleDraft(
            title="Reconnect a registered device",
            article_type=ArticleType.HOW_TO,
            product=prompt_inputs.product,
            module=prompt_inputs.module,
            content=HowToArticle(
                purpose=claim,
                prerequisites=(),
                steps=(ArticleStep("Reconnect the device.", (reference,)),),
                expected_result=claim,
            ),
        )


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _retrieved(
    text: str = "Clear stale registration, then reconnect the device.",
) -> RetrievedKnowledgeChunk:
    access = AccessPolicy("tenant-a", AccessScope.TENANT)
    chunk = KnowledgeChunk(
        chunk_id="chunk-1",
        knowledge_id="knowledge-1",
        source_system="service-manual",
        source_record_id="sync.md",
        source_version="3",
        document_title="Device Sync",
        sequence_number=0,
        text=text,
        start_offset=12,
        end_offset=12 + len(text),
        content_fingerprint=text_fingerprint(text),
        ingestion_fingerprint=_digest("ingestion"),
        normalized_content_fingerprint=_digest("normalized"),
        normalization_strategy_version="normalize-v1",
        access_policy=access,
        strategy_version="chunk-v1",
    )
    return RetrievedKnowledgeChunk(
        chunk,
        rank=1,
        score=1.7,
        strategy_version="hybrid-v1",
    )


def _command() -> GenerateKnowledgeArticleCommand:
    return GenerateKnowledgeArticleCommand(
        request=KnowledgeArticleGenerationRequest(
            subject="Device sync failure",
            article_type=ArticleType.HOW_TO,
            product="Device Service",
            module="Registration",
            business_context="Document the supported recovery path.",
            retrieval_keywords=("firmware", "sync"),
            output_preferences=OutputPreferences(detail_level=DetailLevel.DETAILED),
        ),
        tenant_id="tenant-a",
        groups=("support",),
        prompt_profile=PromptProfileRef(
            profile_id="knowledge-article",
            version="v1",
        ),
        retrieval_limit=4,
    )


def test_retrieves_authorized_evidence_and_preserves_generation_context() -> None:
    retriever = FakeRetriever((_retrieved(),))
    generator = RecordingGenerator()

    result = GenerateKnowledgeArticle(retriever, generator).execute(_command())

    assert result.title == "Reconnect a registered device"
    assert retriever.request is not None
    assert retriever.request.query == (
        "Device sync failure Device Service Registration firmware sync"
    )
    assert retriever.request.access.tenant_id == "tenant-a"
    assert retriever.request.access.groups == ("support",)
    assert retriever.request.limit == 4

    assert generator.prompt_inputs is not None
    assert generator.prompt_inputs.prompt_profile.version == "v1"
    assert generator.prompt_inputs.policy.require_evidence is True
    assert generator.evidence is not None

    excerpt = generator.evidence[0]
    assert excerpt.reference.chunk_id == "chunk-1"
    assert excerpt.reference.knowledge_id == "knowledge-1"
    assert excerpt.reference.source_record_id == "sync.md"
    assert excerpt.reference.source_version == "3"
    assert excerpt.reference.locator == "service-manual:sync.md@v3#chars=12-64"
    assert excerpt.reference.content_fingerprint == text_fingerprint(excerpt.text)


def test_does_not_call_generator_without_authorized_evidence() -> None:
    retriever = FakeRetriever(())
    generator = RecordingGenerator()

    with pytest.raises(LookupError, match="No authorized evidence"):
        GenerateKnowledgeArticle(retriever, generator).execute(_command())

    assert generator.prompt_inputs is None
    assert generator.evidence is None
