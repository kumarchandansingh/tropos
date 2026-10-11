"""Spreadsheet-friendly human review workflow for evidence sufficiency.

The canonical benchmark remains JSON. Reviewers receive CSV packets that can be
opened in Excel/Google Sheets. Import reconstructs reviews against the canonical
benchmark, so reviewer files cannot mutate query/evidence/source provenance.
"""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Iterable

from tropos.evals.contracts import EvalApproval, JsonObject
from tropos.evals.evidence_sufficiency import (
    EvidenceSufficiencyBenchmark,
    EvidenceSufficiencyCase,
    EvidenceSufficiencyLabel,
    EvidenceSufficiencyReason,
    HumanSufficiencyReview,
)

REVIEW_COLUMNS = (
    "Case ID",
    "Split",
    "Query",
    "Evidence",
    "Sources",
    "Reviewer",
    "Review Date",
    "Label",
    "Reason Code",
    "Required Facts",
    "Missing Facts",
    "Confidence",
    "Would you answer?",
    "Notes",
)

ADJUDICATION_COLUMNS = (
    "Case ID",
    "Split",
    "Query",
    "Review Summary",
    "Adjudicator",
    "Adjudicated At",
    "Label",
    "Reason Code",
    "Required Facts",
    "Missing Facts",
    "Confidence",
    "Would you answer?",
    "Notes",
)


def _fact_text(values: Iterable[str]) -> str:
    return "\n".join(values)


def _parse_facts(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(line.strip() for line in value.splitlines() if line.strip()))


def _parse_timestamp(value: str, *, field: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601 with timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed


def _parse_yes_no(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"yes", "y", "true"}:
        return True
    if normalized in {"no", "n", "false"}:
        return False
    raise ValueError("Would you answer? must be YES or NO")


def _parse_review_fields(
    row: dict[str, str],
    *,
    identity_field: str,
    timestamp_field: str,
) -> HumanSufficiencyReview:
    identity = row.get(identity_field, "").strip()
    if not identity:
        raise ValueError(f"{identity_field} is required")
    confidence_text = row.get("Confidence", "").strip()
    try:
        confidence = int(confidence_text)
    except ValueError as exc:
        raise ValueError("Confidence must be an integer from 1 to 5") from exc
    return HumanSufficiencyReview(
        reviewer=identity,
        reviewed_at=_parse_timestamp(row.get(timestamp_field, ""), field=timestamp_field),
        label=EvidenceSufficiencyLabel(row.get("Label", "").strip()),
        reason=EvidenceSufficiencyReason(row.get("Reason Code", "").strip()),
        required_facts=_parse_facts(row.get("Required Facts", "")),
        missing_facts=_parse_facts(row.get("Missing Facts", "")),
        confidence=confidence,
        would_answer=_parse_yes_no(row.get("Would you answer?", "")),
        notes=row.get("Notes", "").strip(),
    )


def export_review_packet(
    benchmark: EvidenceSufficiencyBenchmark,
    path: str | Path,
    *,
    reviewer: str = "",
) -> None:
    """Write candidate cases as an Excel-compatible CSV review packet."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for case in benchmark.cases:
            if case.approval is not EvalApproval.CANDIDATE:
                continue
            writer.writerow(
                {
                    "Case ID": case.case_id,
                    "Split": case.split.value,
                    "Query": case.query,
                    "Evidence": _fact_text(
                        f"{item.evidence_id}: {item.text}" for item in case.evidence
                    ),
                    "Sources": _fact_text(
                        f"{source.source_id} [{source.role.value}] {source.title} — {source.url}"
                        for source in case.source_references
                    ),
                    "Reviewer": reviewer,
                    "Review Date": "",
                    "Label": "",
                    "Reason Code": "",
                    "Required Facts": "",
                    "Missing Facts": "",
                    "Confidence": "",
                    "Would you answer?": "",
                    "Notes": "",
                }
            )


def import_review_packet(
    benchmark: EvidenceSufficiencyBenchmark,
    path: str | Path,
) -> EvidenceSufficiencyBenchmark:
    """Append completed human reviews while preserving canonical case content."""

    reviews_by_case: dict[str, list[HumanSufficiencyReview]] = {}
    known_cases = {case.case_id for case in benchmark.cases}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise ValueError("review packet columns do not match the Tropos review contract")
        for row_number, row in enumerate(reader, start=2):
            case_id = row.get("Case ID", "").strip()
            if not case_id:
                continue
            if case_id not in known_cases:
                raise ValueError(f"row {row_number}: unknown case ID {case_id}")
            if not row.get("Label", "").strip():
                continue
            try:
                review = _parse_review_fields(
                    row,
                    identity_field="Reviewer",
                    timestamp_field="Review Date",
                )
            except ValueError as exc:
                raise ValueError(f"row {row_number} ({case_id}): {exc}") from exc
            reviews_by_case.setdefault(case_id, []).append(review)

    updated_cases: list[EvidenceSufficiencyCase] = []
    for case in benchmark.cases:
        additions = reviews_by_case.get(case.case_id, [])
        existing_reviewers = {review.reviewer for review in case.reviews}
        for review in additions:
            if review.reviewer in existing_reviewers:
                raise ValueError(
                    f"{case.case_id}: reviewer {review.reviewer!r} already has a recorded review"
                )
            existing_reviewers.add(review.reviewer)
        updated_cases.append(replace(case, reviews=(*case.reviews, *additions)))

    return replace(benchmark, cases=tuple(updated_cases))


def agreement_summary(benchmark: EvidenceSufficiencyBenchmark) -> JsonObject:
    """Summarize double-review coverage and observed agreement."""

    double_reviewed = [case for case in benchmark.cases if len(case.reviews) >= 2]
    label_matches = 0
    label_reason_matches = 0
    disagreement_case_ids: list[str] = []
    low_confidence_case_ids: list[str] = []

    for case in double_reviewed:
        first, second = case.reviews[:2]
        label_match = first.label is second.label
        reason_match = first.reason is second.reason
        if label_match:
            label_matches += 1
        if label_match and reason_match:
            label_reason_matches += 1
        if not (label_match and reason_match):
            disagreement_case_ids.append(case.case_id)
        if min(first.confidence, second.confidence) <= 2:
            low_confidence_case_ids.append(case.case_id)

    count = len(double_reviewed)
    return {
        "case_count": len(benchmark.cases),
        "reviewed_case_count": sum(bool(case.reviews) for case in benchmark.cases),
        "double_reviewed_case_count": count,
        "label_agreement": None if count == 0 else label_matches / count,
        "label_reason_agreement": None if count == 0 else label_reason_matches / count,
        "disagreement_case_ids": disagreement_case_ids,
        "low_confidence_case_ids": low_confidence_case_ids,
    }


def export_adjudication_packet(
    benchmark: EvidenceSufficiencyBenchmark,
    path: str | Path,
) -> None:
    """Write reviewed cases for explicit human adjudication."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ADJUDICATION_COLUMNS)
        writer.writeheader()
        for case in benchmark.cases:
            if not case.reviews or case.approval is EvalApproval.APPROVED:
                continue
            review_summary = _fact_text(
                (
                    f"{review.reviewer}: {review.label.value} / {review.reason.value} "
                    f"(confidence {review.confidence}/5)"
                )
                for review in case.reviews
            )
            writer.writerow(
                {
                    "Case ID": case.case_id,
                    "Split": case.split.value,
                    "Query": case.query,
                    "Review Summary": review_summary,
                    "Adjudicator": "",
                    "Adjudicated At": "",
                    "Label": "",
                    "Reason Code": "",
                    "Required Facts": "",
                    "Missing Facts": "",
                    "Confidence": "",
                    "Would you answer?": "",
                    "Notes": "",
                }
            )


def import_adjudication_packet(
    benchmark: EvidenceSufficiencyBenchmark,
    path: str | Path,
) -> EvidenceSufficiencyBenchmark:
    """Apply final adjudications and atomically promote completed cases."""

    adjudications: dict[str, HumanSufficiencyReview] = {}
    cases_by_id = {case.case_id: case for case in benchmark.cases}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ADJUDICATION_COLUMNS:
            raise ValueError("adjudication packet columns do not match the Tropos contract")
        for row_number, row in enumerate(reader, start=2):
            case_id = row.get("Case ID", "").strip()
            if not case_id:
                continue
            case = cases_by_id.get(case_id)
            if case is None:
                raise ValueError(f"row {row_number}: unknown case ID {case_id}")
            if not row.get("Label", "").strip():
                continue
            if not case.reviews:
                raise ValueError(f"row {row_number} ({case_id}): adjudication requires human review")
            if case.approval is EvalApproval.APPROVED:
                raise ValueError(f"row {row_number} ({case_id}): case is already approved")
            if case_id in adjudications:
                raise ValueError(f"row {row_number}: duplicate adjudication for {case_id}")
            try:
                adjudications[case_id] = _parse_review_fields(
                    row,
                    identity_field="Adjudicator",
                    timestamp_field="Adjudicated At",
                )
            except ValueError as exc:
                raise ValueError(f"row {row_number} ({case_id}): {exc}") from exc

    updated_cases = tuple(
        replace(
            case,
            approval=EvalApproval.APPROVED,
            adjudication=adjudications[case.case_id],
        )
        if case.case_id in adjudications
        else case
        for case in benchmark.cases
    )
    return replace(benchmark, cases=updated_cases)


def benchmark_snapshot(benchmark: EvidenceSufficiencyBenchmark) -> JsonObject:
    """Serialize the benchmark without losing review/adjudication lineage."""

    cases: list[JsonObject] = []
    for case in benchmark.cases:
        cases.append(
            {
                "case_id": case.case_id,
                "evidence_set_id": case.evidence_set_id,
                "split": case.split.value,
                "approval": case.approval.value,
                "query": case.query,
                "evidence": [item.snapshot() for item in case.evidence],
                "pattern_ids": list(case.pattern_ids),
                "source_references": [source.snapshot() for source in case.source_references],
                "reviews": [review.snapshot() for review in case.reviews],
                "adjudication": (
                    None if case.adjudication is None else case.adjudication.snapshot()
                ),
                "tags": list(case.tags),
            }
        )
    return {
        "dataset_id": benchmark.dataset_id,
        "version": benchmark.version,
        "notes": benchmark.notes,
        "cases": cases,
    }


def write_benchmark(benchmark: EvidenceSufficiencyBenchmark, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(benchmark_snapshot(benchmark), indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
