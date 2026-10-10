"""Deterministic evaluation for grounded Knowledge Article generation."""

import json
from dataclasses import dataclass
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
from tropos.evals.contracts import (
    EvalApproval,
    EvalCase,
    EvalDataset,
    EvalOrigin,
    EvalScope,
    EvalScore,
    EvalScoreSource,
    EvalSplit,
    JsonObject,
    JsonValue,
)

EVALUATOR_ID = "knowledge-article-deterministic"
EVALUATOR_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class KnowledgeArticleEvalResult:
    case_id: str
    required_section_coverage: float
    citation_alignment: float
    gap_handling: float
    forbidden_behavior_clear: bool
    passed: bool

    def scores(self) -> tuple[EvalScore, ...]:
        return (
            _score(
                "required_section_coverage",
                self.required_section_coverage,
                self.required_section_coverage == 1.0,
            ),
            _score(
                "citation_alignment",
                self.citation_alignment,
                self.citation_alignment == 1.0,
            ),
            _score("gap_handling", self.gap_handling, self.gap_handling == 1.0),
            _score(
                "forbidden_behavior_clear",
                self.forbidden_behavior_clear,
                self.forbidden_behavior_clear,
            ),
        )


def _score(metric: str, value: float | bool, passed: bool) -> EvalScore:
    return EvalScore(
        metric=metric,
        value=value,
        source=EvalScoreSource.DETERMINISTIC,
        evaluator_id=EVALUATOR_ID,
        evaluator_version=EVALUATOR_VERSION,
        passed=passed,
    )


def _object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ValueError("expected JSON array")
    return value


def _text(value: JsonValue) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected non-empty text")
    return value


def _strings(value: JsonValue) -> tuple[str, ...]:
    return tuple(_text(item) for item in _array(value))


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _citation_ids(refs: tuple[EvidenceRef, ...]) -> set[str]:
    return {ref.chunk_id for ref in refs}


def _claims(draft: KnowledgeArticleDraft) -> tuple[EvidenceClaim, ...]:
    content = draft.content
    if isinstance(content, TroubleshootingArticle):
        return (
            content.issue_description,
            *content.symptoms,
            *content.prerequisites,
            content.expected_result,
            *content.exceptions,
            *content.escalation_criteria,
        )
    if isinstance(content, HowToArticle):
        return (
            content.purpose,
            *content.prerequisites,
            content.expected_result,
            *content.next_steps,
            *content.exceptions,
        )
    return (
        content.introduction,
        *(item.answer for item in content.items),
        *content.additional_information,
    )


def _steps(draft: KnowledgeArticleDraft) -> tuple[ArticleStep, ...]:
    content = draft.content
    if isinstance(content, TroubleshootingArticle):
        return (*content.diagnostic_checks, *content.resolution_steps)
    if isinstance(content, HowToArticle):
        return content.steps
    return ()


def _gaps(draft: KnowledgeArticleDraft) -> tuple[ArticleGap, ...]:
    return draft.content.gaps


def _section_presence(draft: KnowledgeArticleDraft) -> dict[str, bool]:
    content = draft.content
    if isinstance(content, TroubleshootingArticle):
        return {
            "issue_description": True,
            "symptoms": bool(content.symptoms),
            "prerequisites": bool(content.prerequisites),
            "diagnostic_checks": bool(content.diagnostic_checks),
            "resolution_steps": bool(content.resolution_steps),
            "expected_result": True,
            "exceptions": bool(content.exceptions),
            "escalation_criteria": bool(content.escalation_criteria),
            "gaps": bool(content.gaps),
        }
    if isinstance(content, HowToArticle):
        return {
            "purpose": True,
            "prerequisites": bool(content.prerequisites),
            "steps": bool(content.steps),
            "expected_result": True,
            "next_steps": bool(content.next_steps),
            "exceptions": bool(content.exceptions),
            "gaps": bool(content.gaps),
        }
    return {
        "introduction": True,
        "items": bool(content.items),
        "additional_information": bool(content.additional_information),
        "gaps": bool(content.gaps),
    }


def _all_text(draft: KnowledgeArticleDraft) -> tuple[str, ...]:
    return (
        *(claim.text for claim in _claims(draft)),
        *(step.instruction for step in _steps(draft)),
        *(gap.description for gap in _gaps(draft)),
    )


def _matching_claims(
    expected_text: str,
    draft: KnowledgeArticleDraft,
) -> tuple[EvidenceClaim | ArticleStep, ...]:
    needle = _norm(expected_text)
    claims: list[EvidenceClaim | ArticleStep] = []
    claims.extend(claim for claim in _claims(draft) if needle in _norm(claim.text))
    claims.extend(step for step in _steps(draft) if needle in _norm(step.instruction))
    return tuple(claims)


def evaluate_knowledge_article(
    case: EvalCase,
    draft: KnowledgeArticleDraft,
) -> KnowledgeArticleEvalResult:
    expected = case.expected
    expected_type = ArticleType(_text(expected["article_type"]))
    if draft.article_type is not expected_type:
        return KnowledgeArticleEvalResult(case.case_id, 0.0, 0.0, 0.0, False, False)

    required_sections = _strings(expected["required_sections"])
    present = _section_presence(draft)
    required_section_coverage = (
        sum(bool(present.get(section)) for section in required_sections) / len(required_sections)
        if required_sections
        else 1.0
    )

    expected_claims = _array(expected["claims"])
    aligned = 0
    for raw in expected_claims:
        row = _object(raw)
        matches = _matching_claims(_text(row["contains"]), draft)
        expected_ids = set(_strings(row["evidence_chunk_ids"]))
        if matches and _citation_ids(matches[0].evidence_refs) == expected_ids:
            aligned += 1
    citation_alignment = aligned / len(expected_claims) if expected_claims else 1.0

    expected_gaps = _array(expected["gaps"])
    matched_gaps = 0
    for raw in expected_gaps:
        row = _object(raw)
        needle = _norm(_text(row["contains"]))
        kind = ArticleGapKind(_text(row["kind"]))
        expected_ids = set(_strings(row["evidence_chunk_ids"]))
        match = next(
            (
                gap
                for gap in _gaps(draft)
                if needle in _norm(gap.description)
                and gap.kind is kind
                and _citation_ids(gap.evidence_refs) == expected_ids
            ),
            None,
        )
        if match is not None:
            matched_gaps += 1
    gap_handling = matched_gaps / len(expected_gaps) if expected_gaps else float(not _gaps(draft))

    forbidden_terms = _strings(expected["forbidden_terms"])
    normalized_text = tuple(_norm(value) for value in _all_text(draft))
    forbidden_behavior_clear = all(
        _norm(term) not in value for term in forbidden_terms for value in normalized_text
    )

    passed = (
        required_section_coverage == 1.0
        and citation_alignment == 1.0
        and gap_handling == 1.0
        and forbidden_behavior_clear
    )
    return KnowledgeArticleEvalResult(
        case_id=case.case_id,
        required_section_coverage=required_section_coverage,
        citation_alignment=citation_alignment,
        gap_handling=gap_handling,
        forbidden_behavior_clear=forbidden_behavior_clear,
        passed=passed,
    )


def load_knowledge_article_dataset(path: Path) -> EvalDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Knowledge Article dataset must be a JSON object")

    cases: list[EvalCase] = []
    for raw_case in _array(raw["cases"]):
        row = _object(raw_case)
        cases.append(
            EvalCase(
                case_id=_text(row["case_id"]),
                purpose=_text(row["purpose"]),
                scope=EvalScope(_text(row["scope"])),
                approval=EvalApproval(_text(row["approval"])),
                origin=EvalOrigin(_text(row["origin"])),
                inputs=_object(row["inputs"]),
                expected=_object(row["expected"]),
                tags=_strings(row.get("tags", [])),
            )
        )

    return EvalDataset(
        dataset_id=_text(raw["dataset_id"]),
        version=_text(raw["version"]),
        capability=_text(raw["capability"]),
        split=EvalSplit(_text(raw["split"])),
        cases=tuple(cases),
    )


def render_scorecard(
    dataset: EvalDataset,
    results: tuple[KnowledgeArticleEvalResult, ...],
) -> str:
    result_by_case = {result.case_id: result for result in results}
    lines = [
        f"# Knowledge Article evaluation — {dataset.dataset_id} {dataset.version}",
        "",
        f"Dataset fingerprint: `{dataset.fingerprint}`",
        "",
        "| Case | Sections | Citations | Gaps | Forbidden clear | Outcome |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for case in dataset.cases:
        result = result_by_case.get(case.case_id)
        if result is None:
            lines.append(f"| {case.case_id} | — | — | — | — | not run |")
            continue
        lines.append(
            "| "
            f"{case.case_id} | "
            f"{result.required_section_coverage:.2f} | "
            f"{result.citation_alignment:.2f} | "
            f"{result.gap_handling:.2f} | "
            f"{'yes' if result.forbidden_behavior_clear else 'no'} | "
            f"{'pass' if result.passed else 'fail'} |"
        )
    return "\n".join(lines) + "\n"
