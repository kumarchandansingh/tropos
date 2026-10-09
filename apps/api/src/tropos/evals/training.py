"""Deterministic evaluation for grounded training procedure extraction."""

from dataclasses import dataclass

from tropos.capabilities.training.procedure import ProcedureDraft


def _norm(value: str) -> str:
    return " ".join(value.lower().split())


@dataclass(frozen=True, slots=True)
class ExpectedClaim:
    contains: str
    evidence_chunk_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExpectedStep(ExpectedClaim):
    pass


@dataclass(frozen=True, slots=True)
class TrainingEvalCase:
    case_id: str
    expected_steps: tuple[ExpectedStep, ...]
    forbidden_step_terms: tuple[str, ...] = ()
    expected_exceptions: tuple[ExpectedClaim, ...] = ()
    expected_gaps: tuple[ExpectedClaim, ...] = ()


@dataclass(frozen=True, slots=True)
class TrainingEvalResult:
    case_id: str
    step_coverage: float
    citation_alignment: float
    exception_separation: bool
    gap_coverage: float
    passed: bool


def _citation_ids(evidence_refs: tuple[object, ...]) -> set[str]:
    return {getattr(ref, "chunk_id") for ref in evidence_refs}


def evaluate_procedure(case: TrainingEvalCase, draft: ProcedureDraft) -> TrainingEvalResult:
    """Score one draft against explicit, human-authored grounded expectations."""

    normalized_steps = tuple(_norm(step.instruction) for step in draft.steps)
    normalized_exceptions = tuple(_norm(item.description) for item in draft.exceptions)
    normalized_gaps = tuple(_norm(item.description) for item in draft.gaps)

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
            if _citation_ids(matching[0].evidence_refs) == set(expected.evidence_chunk_ids):
                aligned_citations += 1

    matched_exceptions = 0
    for expected in case.expected_exceptions:
        expected_text = _norm(expected.contains)
        matching = [
            item
            for item, text in zip(draft.exceptions, normalized_exceptions, strict=True)
            if expected_text in text
        ]
        if matching:
            matched_exceptions += 1
            if _citation_ids(matching[0].evidence_refs) == set(expected.evidence_chunk_ids):
                aligned_citations += 1

    matched_gaps = 0
    for expected in case.expected_gaps:
        expected_text = _norm(expected.contains)
        matching = [
            item
            for item, text in zip(draft.gaps, normalized_gaps, strict=True)
            if expected_text in text
        ]
        if matching:
            matched_gaps += 1
            if _citation_ids(matching[0].evidence_refs) == set(expected.evidence_chunk_ids):
                aligned_citations += 1

    step_coverage = (
        matched_steps / len(case.expected_steps) if case.expected_steps else float(not draft.steps)
    )
    expected_claim_count = (
        len(case.expected_steps) + len(case.expected_exceptions) + len(case.expected_gaps)
    )
    citation_alignment = (
        aligned_citations / expected_claim_count
        if expected_claim_count
        else float(not draft.steps and not draft.exceptions and not draft.gaps)
    )
    exception_separation = all(
        _norm(term) not in step for term in case.forbidden_step_terms for step in normalized_steps
    ) and matched_exceptions == len(case.expected_exceptions)
    gap_coverage = (
        matched_gaps / len(case.expected_gaps)
        if case.expected_gaps
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
