"""Deterministic Knowledge Article adapter tests; no network or credentials required."""

from hashlib import sha256
from typing import Any

import pytest

from tropos.capabilities.resolve.adapters.langchain_knowledge_article_generator import (
    LangChainKnowledgeArticleGenerator,
)
from tropos.capabilities.resolve.application.knowledge_article_request import (
    KnowledgeArticleGenerationRequest,
    PromptProfileRef,
    build_prompt_inputs,
)
from tropos.capabilities.resolve.application.ports.knowledge_article import (
    KnowledgeArticleEvidenceExcerpt,
)
from tropos.core.domain.evidence import EvidenceRef
from tropos.core.domain.knowledge_article import (
    ArticleGapKind,
    ArticleType,
    FAQArticle,
    HowToArticle,
    TroubleshootingArticle,
)


class FakeStructuredModel:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.messages: Any = None

    def invoke(self, messages: Any) -> dict[str, Any]:
        self.messages = messages
        return self.response


class FakeModel:
    def __init__(self, response: dict[str, Any]) -> None:
        self.structured = FakeStructuredModel(response)
        self.schema: Any = None

    def with_structured_output(self, schema: Any) -> FakeStructuredModel:
        self.schema = schema
        return self.structured


def _evidence() -> tuple[KnowledgeArticleEvidenceExcerpt, ...]:
    text = "Clear the stale device registration and reconnect the device."
    return (
        KnowledgeArticleEvidenceExcerpt(
            reference=EvidenceRef(
                chunk_id="chunk-1",
                knowledge_id="knowledge-1",
                source_system="service-manual",
                source_record_id="device-sync.md",
                source_version="4",
                locator="service-manual:device-sync.md@v4#chars=10-70",
                content_fingerprint=sha256(text.encode()).hexdigest(),
            ),
            text=text,
        ),
    )


def _prompt_inputs(article_type: ArticleType):
    request = KnowledgeArticleGenerationRequest(
        subject="Device sync failure",
        article_type=article_type,
        product="Device Service",
        module="Registration",
    )
    return build_prompt_inputs(
        request,
        PromptProfileRef(profile_id="knowledge-article", version="v1"),
    )


def test_generates_grounded_troubleshooting_article_and_resolves_aliases() -> None:
    model = FakeModel(
        {
            "title": "Resolve device sync failure",
            "issue_description": {
                "text": "The device fails to sync.",
                "evidence_ids": ["E1"],
            },
            "symptoms": [{"text": "The device remains disconnected.", "evidence_ids": ["E1"]}],
            "prerequisites": [],
            "diagnostic_checks": [
                {
                    "instruction": "Check the registration state.",
                    "evidence_ids": ["E1"],
                }
            ],
            "resolution_steps": [
                {
                    "instruction": "Clear the stale registration and reconnect.",
                    "evidence_ids": ["E1"],
                }
            ],
            "expected_result": {
                "text": "The device reconnects.",
                "evidence_ids": ["E1"],
            },
            "exceptions": [],
            "escalation_criteria": [],
            "gaps": [
                {
                    "description": "The evidence does not define an escalation threshold.",
                    "kind": "missing_information",
                    "evidence_ids": ["E1"],
                }
            ],
        }
    )

    result = LangChainKnowledgeArticleGenerator(model).generate(
        _prompt_inputs(ArticleType.TROUBLESHOOTING),
        _evidence(),
    )

    assert isinstance(result.content, TroubleshootingArticle)
    assert result.content.resolution_steps[0].evidence_refs[0].chunk_id == "chunk-1"
    assert result.content.gaps[0].kind is ArticleGapKind.MISSING_INFORMATION
    assert result.content.gaps[0].evidence_refs[0].chunk_id == "chunk-1"
    assert model.schema.__name__ == "_TroubleshootingDraft"
    assert model.structured.messages is not None


def test_generates_how_to_article_with_fixed_schema() -> None:
    model = FakeModel(
        {
            "title": "Reconnect a registered device",
            "purpose": {"text": "Reconnect the device.", "evidence_ids": ["E1"]},
            "prerequisites": [],
            "steps": [
                {
                    "instruction": "Clear the stale registration and reconnect.",
                    "evidence_ids": ["E1"],
                }
            ],
            "expected_result": {
                "text": "The device reconnects.",
                "evidence_ids": ["E1"],
            },
            "next_steps": [],
            "exceptions": [],
            "gaps": [],
        }
    )

    result = LangChainKnowledgeArticleGenerator(model).generate(
        _prompt_inputs(ArticleType.HOW_TO),
        _evidence(),
    )

    assert isinstance(result.content, HowToArticle)
    assert model.schema.__name__ == "_HowToDraft"


def test_generates_faq_article_with_fixed_schema() -> None:
    model = FakeModel(
        {
            "title": "Device registration FAQ",
            "introduction": {
                "text": "Registration supports device connectivity.",
                "evidence_ids": ["E1"],
            },
            "items": [
                {
                    "question": "How do I recover stale registration?",
                    "answer": {
                        "text": "Clear the stale registration and reconnect.",
                        "evidence_ids": ["E1"],
                    },
                }
            ],
            "additional_information": [],
            "gaps": [],
        }
    )

    result = LangChainKnowledgeArticleGenerator(model).generate(
        _prompt_inputs(ArticleType.FAQ),
        _evidence(),
    )

    assert isinstance(result.content, FAQArticle)
    assert result.content.items[0].answer.evidence_refs[0].chunk_id == "chunk-1"
    assert model.schema.__name__ == "_FAQDraft"


def test_rejects_fabricated_evidence_alias() -> None:
    model = FakeModel(
        {
            "title": "Reconnect a registered device",
            "purpose": {"text": "Reconnect the device.", "evidence_ids": ["E999"]},
            "prerequisites": [],
            "steps": [
                {
                    "instruction": "Reconnect the device.",
                    "evidence_ids": ["E1"],
                }
            ],
            "expected_result": {
                "text": "The device reconnects.",
                "evidence_ids": ["E1"],
            },
            "next_steps": [],
            "exceptions": [],
            "gaps": [],
        }
    )

    with pytest.raises(ValueError, match="unknown evidence"):
        LangChainKnowledgeArticleGenerator(model).generate(
            _prompt_inputs(ArticleType.HOW_TO),
            _evidence(),
        )


def test_requires_at_least_one_evidence_excerpt() -> None:
    model = FakeModel({})

    with pytest.raises(ValueError, match="At least one"):
        LangChainKnowledgeArticleGenerator(model).generate(
            _prompt_inputs(ArticleType.FAQ),
            (),
        )
