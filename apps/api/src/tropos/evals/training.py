"""Deterministic evaluation for training procedure extraction."""

from dataclasses import dataclass

from tropos.capabilities.training.procedure import ProcedureDraft


def _norm(value: str) -> str:
    return " ".join(value.lower().split())


@dataclass(frozen=True, slots=True)
class ExpectedStep:
    contains: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrainingEvalCase:
    case_id: str
    expected_steps: tuple[ExpectedStep, ...]
    forbidden_step_terms: tuple[str, ...] = ()
    expected_exception_terms: tuple[str, ...] = ()
    expected_gap_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TrainingEvalResult:
    case_id: str
    step_coverage: float
    citation_alignment: float
    exception_separation: bool
    gap_coverage: float
    passed: bool


def evaluate_procedure(case: TrainingEvalCase, draft: ProcedureDraft) -> TrainingEvalResult:
    """Score one draft against explicit, human-authored expectations."""

    normalized_steps = tuple(_norm(step.instruction) for step in draft.steps)
    normalized_exceptions = tuple(_norm(item) for item in draft.exceptions)
    normalized_gaps = tuple(_norm(item) for item in draft.gaps)

    matched_steps = 0
    aligned_citations = 0
    for expected in case.expected_steps:
        expected_text = _norm(expected.contains)
        matching = [
            step
            for step, text in zip(draft.steps, normalized_steps, strict=True)
            if expected_text in text
        ]
        if matching:
            matched_steps += 1
            if set(matching[0].evidence_ids) == set(expected.evidence_ids):
                aligned_citations += 1

    step_coverage = (
        matched_steps / len(case.expected_steps) if case.expected_steps else float(not draft.steps)
    )
    citation_alignment = (
        aligned_citations / len(case.expected_steps)
        if case.expected_steps
        else float(not draft.steps)
    )

    exception_separation = all(
        _norm(term) not in step for term in case.forbidden_step_terms for step in normalized_steps
    ) and all(
        any(_norm(term) in exception for exception in normalized_exceptions)
        for term in case.expected_exception_terms
    )

    matched_gaps = sum(
        any(_norm(term) in gap for gap in normalized_gaps) for term in case.expected_gap_terms
    )
    gap_coverage = (
        matched_gaps / len(case.expected_gap_terms)
        if case.expected_gap_terms
        else float(not draft.gaps)
    )

    passed = (
        step_coverage == 1.0
        and citation_alignment == 1.0
        and exception_separation
        and gap_coverage == 1.0
    )
    return TrainingEvalResult(
        case_id=case.case_id,
        step_coverage=step_coverage,
        citation_alignment=citation_alignment,
        exception_separation=exception_separation,
        gap_coverage=gap_coverage,
        passed=passed,
    )
