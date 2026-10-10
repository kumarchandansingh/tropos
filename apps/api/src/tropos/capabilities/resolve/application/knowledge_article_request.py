"""Typed business intake contracts for grounded Knowledge Article generation."""

from dataclasses import dataclass, field
from enum import StrEnum

from tropos.core.domain.knowledge_article import ArticleType

MAX_BUSINESS_CONTEXT_LENGTH = 1000
MAX_PREFERENCE_ITEMS = 10


def _validate_optional_text(field_name: str, value: str | None) -> None:
    if value is not None and not value.strip():
        raise ValueError(f"{field_name} must not be blank when supplied")


def _validate_terms(field_name: str, values: tuple[str, ...]) -> None:
    if len(values) > MAX_PREFERENCE_ITEMS:
        raise ValueError(f"{field_name} must contain no more than {MAX_PREFERENCE_ITEMS} items")
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} must not contain blank items")
    normalized = tuple(value.casefold() for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicate items")


class DetailLevel(StrEnum):
    STANDARD = "standard"
    DETAILED = "detailed"


@dataclass(frozen=True, slots=True)
class OutputPreferences:
    """Bounded presentation controls available to a business user."""

    detail_level: DetailLevel = DetailLevel.STANDARD
    focus_areas: tuple[str, ...] = ()
    preferred_terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_terms("focus_areas", self.focus_areas)
        _validate_terms("preferred_terms", self.preferred_terms)


@dataclass(frozen=True, slots=True)
class KnowledgeArticleGenerationRequest:
    """Business-owned intent. Governance rules are deliberately absent."""

    subject: str
    article_type: ArticleType
    product: str
    module: str | None = None
    business_context: str | None = None
    retrieval_keywords: tuple[str, ...] = ()
    output_preferences: OutputPreferences = field(default_factory=OutputPreferences)

    def __post_init__(self) -> None:
        if not self.subject.strip():
            raise ValueError("subject must not be blank")
        if not self.product.strip():
            raise ValueError("product must not be blank")
        _validate_optional_text("module", self.module)
        _validate_optional_text("business_context", self.business_context)
        if (
            self.business_context is not None
            and len(self.business_context) > MAX_BUSINESS_CONTEXT_LENGTH
        ):
            raise ValueError("business_context exceeds the supported maximum length")
        _validate_terms("retrieval_keywords", self.retrieval_keywords)


@dataclass(frozen=True, slots=True)
class PromptProfileRef:
    """System-selected prompt profile and immutable version identifier."""

    profile_id: str
    version: str

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("profile_id must not be blank")
        if not self.version.strip():
            raise ValueError("version must not be blank")


@dataclass(frozen=True, slots=True)
class KnowledgeArticleGenerationPolicy:
    """Non-editable generation invariants owned by Tropos."""

    require_evidence: bool = field(default=True, init=False)
    surface_missing_information: bool = field(default=True, init=False)
    surface_conflicts: bool = field(default=True, init=False)
    allow_unsupported_claims: bool = field(default=False, init=False)
    fixed_article_structure: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class KnowledgeArticleRetrievalIntent:
    """Deterministic retrieval inputs derived from the business request."""

    subject: str
    article_type: ArticleType
    product: str
    module: str | None
    keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeArticlePromptInputs:
    """Structured generation inputs assembled before provider invocation."""

    subject: str
    article_type: ArticleType
    product: str
    module: str | None
    business_context: str | None
    output_preferences: OutputPreferences
    prompt_profile: PromptProfileRef
    policy: KnowledgeArticleGenerationPolicy


def build_retrieval_intent(
    request: KnowledgeArticleGenerationRequest,
) -> KnowledgeArticleRetrievalIntent:
    return KnowledgeArticleRetrievalIntent(
        subject=request.subject,
        article_type=request.article_type,
        product=request.product,
        module=request.module,
        keywords=request.retrieval_keywords,
    )


def build_prompt_inputs(
    request: KnowledgeArticleGenerationRequest,
    prompt_profile: PromptProfileRef,
) -> KnowledgeArticlePromptInputs:
    return KnowledgeArticlePromptInputs(
        subject=request.subject,
        article_type=request.article_type,
        product=request.product,
        module=request.module,
        business_context=request.business_context,
        output_preferences=request.output_preferences,
        prompt_profile=prompt_profile,
        policy=KnowledgeArticleGenerationPolicy(),
    )
