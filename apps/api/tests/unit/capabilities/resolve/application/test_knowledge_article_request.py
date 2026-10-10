import pytest

from tropos.capabilities.resolve.application.knowledge_article_request import (
    MAX_BUSINESS_CONTEXT_LENGTH,
    DetailLevel,
    KnowledgeArticleGenerationPolicy,
    KnowledgeArticleGenerationRequest,
    OutputPreferences,
    PromptProfileRef,
    build_prompt_inputs,
    build_retrieval_intent,
)
from tropos.core.domain.knowledge_article import ArticleType


def _request() -> KnowledgeArticleGenerationRequest:
    return KnowledgeArticleGenerationRequest(
        subject="Device fails to sync after firmware update",
        article_type=ArticleType.TROUBLESHOOTING,
        product="Device Service",
        module="Registration",
        business_context="Emphasize checks required before escalation.",
        retrieval_keywords=("firmware", "sync", "registration"),
        output_preferences=OutputPreferences(
            detail_level=DetailLevel.DETAILED,
            focus_areas=("diagnostics", "escalation"),
            preferred_terms=("device registration",),
        ),
    )


def test_request_builds_deterministic_retrieval_intent() -> None:
    request = _request()

    first = build_retrieval_intent(request)
    second = build_retrieval_intent(request)

    assert first == second
    assert first.subject == request.subject
    assert first.keywords == ("firmware", "sync", "registration")


def test_request_builds_deterministic_prompt_inputs() -> None:
    request = _request()
    profile = PromptProfileRef(profile_id="knowledge-article", version="v1")

    first = build_prompt_inputs(request, profile)
    second = build_prompt_inputs(request, profile)

    assert first == second
    assert first.prompt_profile == profile
    assert first.output_preferences.detail_level is DetailLevel.DETAILED


def test_business_user_cannot_override_generation_invariants() -> None:
    with pytest.raises(TypeError):
        KnowledgeArticleGenerationPolicy(require_evidence=False)  # type: ignore[call-arg]

    policy = KnowledgeArticleGenerationPolicy()

    assert policy.require_evidence is True
    assert policy.surface_missing_information is True
    assert policy.surface_conflicts is True
    assert policy.allow_unsupported_claims is False
    assert policy.fixed_article_structure is True


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("subject", {"subject": ""}),
        ("product", {"product": ""}),
        ("module", {"module": " "}),
    ],
)
def test_request_rejects_blank_required_or_optional_text(
    field_name: str,
    kwargs: dict[str, str],
) -> None:
    base = {
        "subject": "Device sync failure",
        "article_type": ArticleType.TROUBLESHOOTING,
        "product": "Device Service",
    }
    base.update(kwargs)

    with pytest.raises(ValueError, match=field_name):
        KnowledgeArticleGenerationRequest(**base)  # type: ignore[arg-type]


def test_request_limits_business_context_length() -> None:
    with pytest.raises(ValueError, match="business_context"):
        KnowledgeArticleGenerationRequest(
            subject="Device sync failure",
            article_type=ArticleType.TROUBLESHOOTING,
            product="Device Service",
            business_context="x" * (MAX_BUSINESS_CONTEXT_LENGTH + 1),
        )


def test_output_preferences_reject_duplicate_terms_case_insensitively() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        OutputPreferences(
            preferred_terms=("Device Registration", "device registration")
        )


def test_request_rejects_blank_retrieval_keyword() -> None:
    with pytest.raises(ValueError, match="retrieval_keywords"):
        KnowledgeArticleGenerationRequest(
            subject="Device sync failure",
            article_type=ArticleType.TROUBLESHOOTING,
            product="Device Service",
            retrieval_keywords=("sync", ""),
        )


def test_prompt_profile_requires_stable_identity_and_version() -> None:
    with pytest.raises(ValueError, match="profile_id"):
        PromptProfileRef(profile_id="", version="v1")

    with pytest.raises(ValueError, match="version"):
        PromptProfileRef(profile_id="knowledge-article", version="")
