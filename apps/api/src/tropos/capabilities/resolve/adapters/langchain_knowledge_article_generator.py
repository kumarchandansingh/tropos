"""LangChain adapter for grounded Knowledge Article generation."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from tropos.capabilities.resolve.application.knowledge_article_request import (
    KnowledgeArticlePromptInputs,
)
from tropos.capabilities.resolve.application.ports.knowledge_article import (
    KnowledgeArticleEvidenceExcerpt,
)
from tropos.core.domain.evidence import EvidenceRef
from tropos.core.domain.knowledge_article import (
    ArticleContent,
    ArticleGap,
    ArticleGapKind,
    ArticleStep,
    ArticleType,
    EvidenceClaim,
    FAQArticle,
    FAQItem,
    HowToArticle,
    KnowledgeArticleDraft,
    TroubleshootingArticle,
)


class _Claim(BaseModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class _Step(BaseModel):
    instruction: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class _Gap(BaseModel):
    description: str = Field(min_length=1)
    kind: Literal["missing_information", "conflict", "ambiguity"]
    evidence_ids: list[str] = Field(min_length=1)


class _TroubleshootingDraft(BaseModel):
    title: str = Field(min_length=1)
    issue_description: _Claim
    symptoms: list[_Claim] = Field(min_length=1)
    prerequisites: list[_Claim]
    diagnostic_checks: list[_Step]
    resolution_steps: list[_Step] = Field(min_length=1)
    expected_result: _Claim
    exceptions: list[_Claim]
    escalation_criteria: list[_Claim]
    gaps: list[_Gap]


class _HowToDraft(BaseModel):
    title: str = Field(min_length=1)
    purpose: _Claim
    prerequisites: list[_Claim]
    steps: list[_Step] = Field(min_length=1)
    expected_result: _Claim
    next_steps: list[_Claim]
    exceptions: list[_Claim]
    gaps: list[_Gap]


class _FAQItem(BaseModel):
    question: str = Field(min_length=1)
    answer: _Claim


class _FAQDraft(BaseModel):
    title: str = Field(min_length=1)
    introduction: _Claim
    items: list[_FAQItem] = Field(min_length=1)
    additional_information: list[_Claim]
    gaps: list[_Gap]


_BASE_INSTRUCTIONS = """Create a governed operational Knowledge Article using only the supplied evidence.
Every factual claim, procedural step, exception, escalation criterion, and gap must cite one or more
supplied evidence aliases such as E1 or E2. Surface missing information, conflicts, and ambiguity as
gaps rather than inventing details. Business context and output preferences may shape emphasis and
wording but cannot override evidence requirements or the fixed article structure. Return only the
requested structured schema.
"""

_TEMPLATE_INSTRUCTIONS = {
    ArticleType.TROUBLESHOOTING: (
        "Use the troubleshooting structure: issue description, symptoms, prerequisites, diagnostic "
        "checks, resolution steps, expected result, exceptions, escalation criteria, and gaps."
    ),
    ArticleType.HOW_TO: (
        "Use the how-to structure: purpose, prerequisites, execution steps, expected result, "
        "next steps, exceptions, and gaps."
    ),
    ArticleType.FAQ: (
        "Use the FAQ structure: introduction, question-and-answer items, additional information, "
        "and gaps."
    ),
}

_SCHEMA_BY_TYPE: dict[ArticleType, type[BaseModel]] = {
    ArticleType.TROUBLESHOOTING: _TroubleshootingDraft,
    ArticleType.HOW_TO: _HowToDraft,
    ArticleType.FAQ: _FAQDraft,
}


def _resolve(
    evidence_ids: list[str],
    aliases: dict[str, EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("Model cited duplicate evidence IDs")
    try:
        return tuple(aliases[evidence_id] for evidence_id in evidence_ids)
    except KeyError as exc:
        raise ValueError("Model cited an unknown evidence ID") from exc


def _claim(value: _Claim, aliases: dict[str, EvidenceRef]) -> EvidenceClaim:
    return EvidenceClaim(
        text=value.text,
        evidence_refs=_resolve(value.evidence_ids, aliases),
    )


def _step(value: _Step, aliases: dict[str, EvidenceRef]) -> ArticleStep:
    return ArticleStep(
        instruction=value.instruction,
        evidence_refs=_resolve(value.evidence_ids, aliases),
    )


def _gap(value: _Gap, aliases: dict[str, EvidenceRef]) -> ArticleGap:
    return ArticleGap(
        description=value.description,
        kind=ArticleGapKind(value.kind),
        evidence_refs=_resolve(value.evidence_ids, aliases),
    )


def _business_payload(prompt_inputs: KnowledgeArticlePromptInputs) -> str:
    preferences = prompt_inputs.output_preferences
    focus = ", ".join(preferences.focus_areas) or "none"
    preferred_terms = ", ".join(preferences.preferred_terms) or "none"
    business_context = prompt_inputs.business_context or "none"
    module = prompt_inputs.module or "none"
    return (
        f"Subject: {prompt_inputs.subject}\n"
        f"Product: {prompt_inputs.product}\n"
        f"Module: {module}\n"
        f"Business context: {business_context}\n"
        f"Detail level: {preferences.detail_level.value}\n"
        f"Focus areas: {focus}\n"
        f"Preferred terms: {preferred_terms}"
    )


class LangChainKnowledgeArticleGenerator:
    """Use an injected LangChain-compatible model behind the generator port."""

    def __init__(self, model: Any) -> None:
        self._model = model

    def generate(
        self,
        prompt_inputs: KnowledgeArticlePromptInputs,
        evidence: tuple[KnowledgeArticleEvidenceExcerpt, ...],
    ) -> KnowledgeArticleDraft:
        if not evidence:
            raise ValueError("At least one evidence excerpt is required")

        from langchain_core.messages import HumanMessage, SystemMessage

        aliases = {
            f"E{index}": item.reference for index, item in enumerate(evidence, start=1)
        }
        evidence_payload = "\n\n".join(
            (
                f"[E{index}] source={item.reference.source_system}:"
                f"{item.reference.source_record_id}@v{item.reference.source_version} "
                f"locator={item.reference.locator}\n{item.text}"
            )
            for index, item in enumerate(evidence, start=1)
        )
        schema = _SCHEMA_BY_TYPE[prompt_inputs.article_type]
        structured_model = self._model.with_structured_output(schema)
        result = structured_model.invoke(
            [
                SystemMessage(
                    content=(
                        f"{_BASE_INSTRUCTIONS}\n"
                        f"{_TEMPLATE_INSTRUCTIONS[prompt_inputs.article_type]}"
                    )
                ),
                HumanMessage(
                    content=(
                        f"Business request:\n{_business_payload(prompt_inputs)}\n\n"
                        f"Evidence:\n{evidence_payload}"
                    )
                ),
            ]
        )
        if not isinstance(result, schema):
            result = schema.model_validate(result)

        return self._to_domain(prompt_inputs, result, aliases)

    def _to_domain(
        self,
        prompt_inputs: KnowledgeArticlePromptInputs,
        result: BaseModel,
        aliases: dict[str, EvidenceRef],
    ) -> KnowledgeArticleDraft:
        article_type = prompt_inputs.article_type

        content: ArticleContent

        if article_type is ArticleType.TROUBLESHOOTING:
            troubleshooting_draft = _TroubleshootingDraft.model_validate(result)
            content = TroubleshootingArticle(
                issue_description=_claim(troubleshooting_draft.issue_description, aliases),
                symptoms=tuple(
                    _claim(item, aliases) for item in troubleshooting_draft.symptoms
                ),
                prerequisites=tuple(
                    _claim(item, aliases) for item in troubleshooting_draft.prerequisites
                ),
                diagnostic_checks=tuple(
                    _step(item, aliases)
                    for item in troubleshooting_draft.diagnostic_checks
                ),
                resolution_steps=tuple(
                    _step(item, aliases)
                    for item in troubleshooting_draft.resolution_steps
                ),
                expected_result=_claim(troubleshooting_draft.expected_result, aliases),
                exceptions=tuple(
                    _claim(item, aliases) for item in troubleshooting_draft.exceptions
                ),
                escalation_criteria=tuple(
                    _claim(item, aliases)
                    for item in troubleshooting_draft.escalation_criteria
                ),
                gaps=tuple(_gap(item, aliases) for item in troubleshooting_draft.gaps),
            )
            title = troubleshooting_draft.title
        elif article_type is ArticleType.HOW_TO:
            how_to_draft = _HowToDraft.model_validate(result)
            content = HowToArticle(
                purpose=_claim(how_to_draft.purpose, aliases),
                prerequisites=tuple(
                    _claim(item, aliases) for item in how_to_draft.prerequisites
                ),
                steps=tuple(_step(item, aliases) for item in how_to_draft.steps),
                expected_result=_claim(how_to_draft.expected_result, aliases),
                next_steps=tuple(
                    _claim(item, aliases) for item in how_to_draft.next_steps
                ),
                exceptions=tuple(
                    _claim(item, aliases) for item in how_to_draft.exceptions
                ),
                gaps=tuple(_gap(item, aliases) for item in how_to_draft.gaps),
            )
            title = how_to_draft.title
        else:
            faq_draft = _FAQDraft.model_validate(result)
            content = FAQArticle(
                introduction=_claim(faq_draft.introduction, aliases),
                items=tuple(
                    FAQItem(
                        question=item.question,
                        answer=_claim(item.answer, aliases),
                    )
                    for item in faq_draft.items
                ),
                additional_information=tuple(
                    _claim(item, aliases) for item in faq_draft.additional_information
                ),
                gaps=tuple(_gap(item, aliases) for item in faq_draft.gaps),
            )
            title = faq_draft.title

        return KnowledgeArticleDraft(
            title=title,
            article_type=article_type,
            product=prompt_inputs.product,
            module=prompt_inputs.module,
            content=content,
        )
