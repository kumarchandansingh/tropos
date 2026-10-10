"""Canonical grounded Knowledge Article contracts shared across Tropos capabilities."""

from dataclasses import dataclass
from enum import StrEnum

from tropos.core.domain.evidence import EvidenceRef


class ArticleType(StrEnum):
    TROUBLESHOOTING = "troubleshooting"
    HOW_TO = "how_to"
    FAQ = "faq"


class ArticleGapKind(StrEnum):
    MISSING_INFORMATION = "missing_information"
    CONFLICT = "conflict"
    AMBIGUITY = "ambiguity"


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    text: str
    evidence_refs: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Evidence claims require non-empty text")
        if not self.evidence_refs:
            raise ValueError("Evidence claims require supporting evidence")


@dataclass(frozen=True, slots=True)
class ArticleStep:
    instruction: str
    evidence_refs: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if not self.instruction.strip():
            raise ValueError("Article steps require non-empty instructions")
        if not self.evidence_refs:
            raise ValueError("Article steps require supporting evidence")


@dataclass(frozen=True, slots=True)
class ArticleGap:
    description: str
    kind: ArticleGapKind
    evidence_refs: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("Article gaps require non-empty descriptions")
        if not self.evidence_refs:
            raise ValueError("Article gaps require contextual evidence")


@dataclass(frozen=True, slots=True)
class TroubleshootingArticle:
    issue_description: EvidenceClaim
    symptoms: tuple[EvidenceClaim, ...]
    prerequisites: tuple[EvidenceClaim, ...]
    diagnostic_checks: tuple[ArticleStep, ...]
    resolution_steps: tuple[ArticleStep, ...]
    expected_result: EvidenceClaim
    exceptions: tuple[EvidenceClaim, ...] = ()
    escalation_criteria: tuple[EvidenceClaim, ...] = ()
    gaps: tuple[ArticleGap, ...] = ()

    def __post_init__(self) -> None:
        if not self.symptoms:
            raise ValueError("Troubleshooting articles require at least one symptom")
        if not self.resolution_steps:
            raise ValueError("Troubleshooting articles require resolution steps")


@dataclass(frozen=True, slots=True)
class HowToArticle:
    purpose: EvidenceClaim
    prerequisites: tuple[EvidenceClaim, ...]
    steps: tuple[ArticleStep, ...]
    expected_result: EvidenceClaim
    next_steps: tuple[EvidenceClaim, ...] = ()
    exceptions: tuple[EvidenceClaim, ...] = ()
    gaps: tuple[ArticleGap, ...] = ()

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("How-to articles require at least one step")


@dataclass(frozen=True, slots=True)
class FAQItem:
    question: str
    answer: EvidenceClaim

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("FAQ questions must not be blank")


@dataclass(frozen=True, slots=True)
class FAQArticle:
    introduction: EvidenceClaim
    items: tuple[FAQItem, ...]
    additional_information: tuple[EvidenceClaim, ...] = ()
    gaps: tuple[ArticleGap, ...] = ()

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("FAQ articles require at least one question and answer")


ArticleContent = TroubleshootingArticle | HowToArticle | FAQArticle


@dataclass(frozen=True, slots=True)
class KnowledgeArticleDraft:
    title: str
    article_type: ArticleType
    product: str
    content: ArticleContent
    module: str | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Knowledge Article title must not be blank")
        if not self.product.strip():
            raise ValueError("Knowledge Article product must not be blank")
        if self.module is not None and not self.module.strip():
            raise ValueError("Knowledge Article module must not be blank when supplied")
        if any(not tag.strip() for tag in self.tags):
            raise ValueError("Knowledge Article tags must not contain blanks")

        expected_type = {
            TroubleshootingArticle: ArticleType.TROUBLESHOOTING,
            HowToArticle: ArticleType.HOW_TO,
            FAQArticle: ArticleType.FAQ,
        }[type(self.content)]
        if self.article_type is not expected_type:
            raise ValueError("Knowledge Article type must match the supplied content template")
