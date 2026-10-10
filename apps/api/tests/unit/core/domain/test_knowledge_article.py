import pytest

from tropos.core.domain.evidence import EvidenceRef
from tropos.core.domain.knowledge_article import (
    ArticleStep,
    ArticleType,
    EvidenceClaim,
    FAQArticle,
    FAQItem,
    HowToArticle,
    KnowledgeArticleDraft,
    TroubleshootingArticle,
)


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        chunk_id="chunk-1",
        knowledge_id="knowledge-1",
        source_system="test",
        source_record_id="record-1",
        source_version="1",
        locator="test:record-1@v1#chars=0-10",
        content_fingerprint="fingerprint-1",
    )


def _claim(text: str = "Supported claim") -> EvidenceClaim:
    return EvidenceClaim(text=text, evidence_refs=(_evidence(),))


def _step(text: str = "Perform the supported action") -> ArticleStep:
    return ArticleStep(instruction=text, evidence_refs=(_evidence(),))


def test_troubleshooting_article_uses_fixed_required_sections() -> None:
    content = TroubleshootingArticle(
        issue_description=_claim("Device does not sync"),
        symptoms=(_claim("Sync status remains pending"),),
        prerequisites=(),
        diagnostic_checks=(_step("Check device registration status"),),
        resolution_steps=(_step("Clear stale registration"),),
        expected_result=_claim("Device returns to connected status"),
    )

    article = KnowledgeArticleDraft(
        title="Resolve device sync failure",
        article_type=ArticleType.TROUBLESHOOTING,
        product="Device Service",
        content=content,
    )

    assert article.content is content
    assert article.article_type is ArticleType.TROUBLESHOOTING


def test_how_to_article_requires_at_least_one_step() -> None:
    with pytest.raises(ValueError, match="at least one step"):
        HowToArticle(
            purpose=_claim(),
            prerequisites=(),
            steps=(),
            expected_result=_claim(),
        )


def test_faq_article_requires_at_least_one_question() -> None:
    with pytest.raises(ValueError, match="at least one question"):
        FAQArticle(introduction=_claim(), items=())


def test_faq_questions_and_answers_are_structured() -> None:
    content = FAQArticle(
        introduction=_claim("Common device registration questions"),
        items=(
            FAQItem(
                question="How do I verify registration?",
                answer=_claim("Open the device status page"),
            ),
        ),
    )

    article = KnowledgeArticleDraft(
        title="Device registration FAQ",
        article_type=ArticleType.FAQ,
        product="Device Service",
        content=content,
    )

    assert article.content.items[0].question == "How do I verify registration?"


def test_article_type_must_match_fixed_content_template() -> None:
    content = HowToArticle(
        purpose=_claim(),
        prerequisites=(),
        steps=(_step(),),
        expected_result=_claim(),
    )

    with pytest.raises(ValueError, match="type must match"):
        KnowledgeArticleDraft(
            title="Wrong template",
            article_type=ArticleType.FAQ,
            product="Device Service",
            content=content,
        )


@pytest.mark.parametrize(
    ("title", "product"),
    [
        ("", "Device Service"),
        ("Valid title", ""),
    ],
)
def test_article_requires_non_blank_metadata(title: str, product: str) -> None:
    content = HowToArticle(
        purpose=_claim(),
        prerequisites=(),
        steps=(_step(),),
        expected_result=_claim(),
    )

    with pytest.raises(ValueError):
        KnowledgeArticleDraft(
            title=title,
            article_type=ArticleType.HOW_TO,
            product=product,
            content=content,
        )
