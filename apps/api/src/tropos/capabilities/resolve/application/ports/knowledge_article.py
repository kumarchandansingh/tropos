"""Provider-neutral Knowledge Article generation boundary."""

from dataclasses import dataclass
from typing import Protocol

from tropos.capabilities.resolve.application.knowledge_article_request import (
    KnowledgeArticlePromptInputs,
)
from tropos.core.domain.evidence import EvidenceRef
from tropos.core.domain.knowledge_article import KnowledgeArticleDraft


@dataclass(frozen=True, slots=True)
class KnowledgeArticleEvidenceExcerpt:
    reference: EvidenceRef
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Knowledge Article evidence excerpts require non-empty text")


class KnowledgeArticleGenerator(Protocol):
    """Generate a grounded draft from structured inputs and governed evidence."""

    def generate(
        self,
        prompt_inputs: KnowledgeArticlePromptInputs,
        evidence: tuple[KnowledgeArticleEvidenceExcerpt, ...],
    ) -> KnowledgeArticleDraft: ...
