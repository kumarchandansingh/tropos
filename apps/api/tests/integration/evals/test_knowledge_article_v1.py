from hashlib import sha256
from pathlib import Path

from tropos.core.domain.evidence import EvidenceRef
from tropos.core.domain.knowledge_article import (
    ArticleGap,
    ArticleGapKind,
    ArticleStep,
    ArticleType,
    EvidenceClaim,
    HowToArticle,
    KnowledgeArticleDraft,
    TroubleshootingArticle,
)
from tropos.evals.contracts import EvalCase
from tropos.evals.knowledge_article import (
    evaluate_knowledge_article,
    load_knowledge_article_dataset,
    render_scorecard,
)

DATASET = (
    Path(__file__).parents[3]
    / "evals"
    / "resolve"
    / "knowledge_article_v1.json"
)


def _ref(chunk_id: str) -> EvidenceRef:
    return EvidenceRef(
        chunk_id=chunk_id,
        knowledge_id=f"knowledge-{chunk_id}",
        source_system="synthetic-eval",
        source_record_id=f"{chunk_id}.txt",
        source_version="1",
        locator=f"synthetic:{chunk_id}",
        content_fingerprint=sha256(chunk_id.encode()).hexdigest(),
    )


def _claim(text: str, *chunk_ids: str) -> EvidenceClaim:
    return EvidenceClaim(text, tuple(_ref(chunk_id) for chunk_id in chunk_ids))


def _step(text: str, *chunk_ids: str) -> ArticleStep:
    return ArticleStep(text, tuple(_ref(chunk_id) for chunk_id in chunk_ids))


def _gap(
    text: str,
    kind: ArticleGapKind,
    *chunk_ids: str,
) -> ArticleGap:
    return ArticleGap(
        text,
        kind,
        tuple(_ref(chunk_id) for chunk_id in chunk_ids),
    )


def _case(case_id: str) -> EvalCase:
    dataset = load_knowledge_article_dataset(DATASET)
    return next(case for case in dataset.cases if case.case_id == case_id)


def test_dataset_is_versioned_approved_and_fingerprinted() -> None:
    dataset = load_knowledge_article_dataset(DATASET)

    assert dataset.dataset_id == "tropos-resolve-knowledge-article-v1"
    assert dataset.version == "v1"
    assert len(dataset.fingerprint) == 64
    assert {case.approval.value for case in dataset.cases} == {"approved"}
    assert {case.case_id for case in dataset.cases} == {
        "normal-how-to-device-reconnect",
        "missing-information-becomes-gap",
        "conflicting-evidence-becomes-gap",
        "exception-and-escalation-remain-separate",
    }


def test_good_normal_how_to_passes_all_dimensions() -> None:
    case = _case("normal-how-to-device-reconnect")
    draft = KnowledgeArticleDraft(
        title="Reconnect a device",
        article_type=ArticleType.HOW_TO,
        product="Device Service",
        content=HowToArticle(
            purpose=_claim(
                "Clear stale registration before reconnecting.",
                "ka-normal-1",
            ),
            prerequisites=(),
            steps=(
                _step("Clear the stale registration.", "ka-normal-1"),
                _step("Reconnect the device.", "ka-normal-2"),
            ),
            expected_result=_claim(
                "The device status becomes Connected.",
                "ka-normal-2",
            ),
        ),
    )

    result = evaluate_knowledge_article(case, draft)

    assert result.required_section_coverage == 1.0
    assert result.citation_alignment == 1.0
    assert result.gap_handling == 1.0
    assert result.forbidden_behavior_clear is True
    assert result.passed is True


def test_wrong_citation_fails_even_when_wording_is_correct() -> None:
    case = _case("normal-how-to-device-reconnect")
    draft = KnowledgeArticleDraft(
        title="Reconnect a device",
        article_type=ArticleType.HOW_TO,
        product="Device Service",
        content=HowToArticle(
            purpose=_claim(
                "Clear stale registration before reconnecting.",
                "ka-normal-2",
            ),
            prerequisites=(),
            steps=(
                _step("Clear the stale registration.", "ka-normal-2"),
                _step("Reconnect the device.", "ka-normal-2"),
            ),
            expected_result=_claim(
                "The device status becomes Connected.",
                "ka-normal-2",
            ),
        ),
    )

    result = evaluate_knowledge_article(case, draft)

    assert result.citation_alignment < 1.0
    assert result.passed is False


def test_unsupported_step_is_rejected_by_forbidden_behavior_check() -> None:
    case = _case("normal-how-to-device-reconnect")
    draft = KnowledgeArticleDraft(
        title="Reconnect a device",
        article_type=ArticleType.HOW_TO,
        product="Device Service",
        content=HowToArticle(
            purpose=_claim(
                "Clear stale registration before reconnecting.",
                "ka-normal-1",
            ),
            prerequisites=(),
            steps=(
                _step("Clear the stale registration.", "ka-normal-1"),
                _step("Reconnect the device.", "ka-normal-2"),
                _step("Factory reset the device.", "ka-normal-2"),
            ),
            expected_result=_claim(
                "The device status becomes Connected.",
                "ka-normal-2",
            ),
        ),
    )

    result = evaluate_knowledge_article(case, draft)

    assert result.forbidden_behavior_clear is False
    assert result.passed is False


def test_missing_information_requires_typed_grounded_gap() -> None:
    case = _case("missing-information-becomes-gap")
    draft = KnowledgeArticleDraft(
        title="Resolve disconnected device",
        article_type=ArticleType.TROUBLESHOOTING,
        product="Device Service",
        content=TroubleshootingArticle(
            issue_description=_claim(
                "The device remains disconnected.",
                "ka-missing-1",
            ),
            symptoms=(
                _claim("Device status is disconnected.", "ka-missing-1"),
            ),
            prerequisites=(),
            diagnostic_checks=(),
            resolution_steps=(
                _step(
                    "Clear stale registration and retry the connection.",
                    "ka-missing-1",
                ),
            ),
            expected_result=_claim(
                "The device can reconnect after the supported retry.",
                "ka-missing-1",
            ),
            gaps=(
                _gap(
                    "The escalation threshold is not specified.",
                    ArticleGapKind.MISSING_INFORMATION,
                    "ka-missing-2",
                ),
            ),
        ),
    )

    result = evaluate_knowledge_article(case, draft)

    assert result.gap_handling == 1.0
    assert result.passed is True


def test_conflicting_evidence_requires_conflict_gap_with_both_sources() -> None:
    case = _case("conflicting-evidence-becomes-gap")
    draft = KnowledgeArticleDraft(
        title="Registration retry policy conflict",
        article_type=ArticleType.TROUBLESHOOTING,
        product="Device Service",
        content=TroubleshootingArticle(
            issue_description=_claim(
                "The sources disagree on retry behavior.",
                "ka-conflict-1",
                "ka-conflict-2",
            ),
            symptoms=(
                _claim(
                    "Registration has failed.",
                    "ka-conflict-1",
                    "ka-conflict-2",
                ),
            ),
            prerequisites=(),
            diagnostic_checks=(),
            resolution_steps=(
                _step(
                    "Do not choose a retry policy until the conflict is resolved.",
                    "ka-conflict-1",
                    "ka-conflict-2",
                ),
            ),
            expected_result=_claim(
                "A reviewed policy determines the supported next action.",
                "ka-conflict-1",
                "ka-conflict-2",
            ),
            gaps=(
                _gap(
                    "Conflict: one source says retry once while another says not to retry.",
                    ArticleGapKind.CONFLICT,
                    "ka-conflict-1",
                    "ka-conflict-2",
                ),
            ),
        ),
    )

    result = evaluate_knowledge_article(case, draft)

    assert result.gap_handling == 1.0
    assert result.forbidden_behavior_clear is True
    assert result.passed is True


def test_exception_and_escalation_sections_are_required_when_expected() -> None:
    case = _case("exception-and-escalation-remain-separate")
    draft = KnowledgeArticleDraft(
        title="Device registration recovery",
        article_type=ArticleType.TROUBLESHOOTING,
        product="Device Service",
        content=TroubleshootingArticle(
            issue_description=_claim(
                "Device registration recovery is required.",
                "ka-exception-1",
            ),
            symptoms=(
                _claim(
                    "The device cannot reconnect with stale registration.",
                    "ka-exception-1",
                ),
            ),
            prerequisites=(),
            diagnostic_checks=(),
            resolution_steps=(
                _step(
                    "Clear the stale entry and reconnect the device.",
                    "ka-exception-1",
                ),
            ),
            expected_result=_claim(
                "The standard device reconnects.",
                "ka-exception-1",
            ),
            exceptions=(
                _claim(
                    "If the certificate is revoked, do not reconnect.",
                    "ka-exception-2",
                ),
            ),
            escalation_criteria=(
                _claim(
                    "Escalate confirmed revoked certificates to the security operations queue.",
                    "ka-exception-3",
                ),
            ),
        ),
    )

    result = evaluate_knowledge_article(case, draft)

    assert result.required_section_coverage == 1.0
    assert result.citation_alignment == 1.0
    assert result.passed is True


def test_scorecard_is_human_readable_and_shows_not_run_cases() -> None:
    dataset = load_knowledge_article_dataset(DATASET)
    case = _case("normal-how-to-device-reconnect")
    draft = KnowledgeArticleDraft(
        title="Reconnect a device",
        article_type=ArticleType.HOW_TO,
        product="Device Service",
        content=HowToArticle(
            purpose=_claim(
                "Clear stale registration before reconnecting.",
                "ka-normal-1",
            ),
            prerequisites=(),
            steps=(
                _step("Clear the stale registration.", "ka-normal-1"),
                _step("Reconnect the device.", "ka-normal-2"),
            ),
            expected_result=_claim(
                "The device status becomes Connected.",
                "ka-normal-2",
            ),
        ),
    )
    result = evaluate_knowledge_article(case, draft)

    report = render_scorecard(dataset, (result,))

    assert "Dataset fingerprint:" in report
    assert "normal-how-to-device-reconnect" in report
    assert "| 1.00 | 1.00 | 1.00 | yes | pass |" in report
    assert "missing-information-becomes-gap" in report
    assert "not run" in report
