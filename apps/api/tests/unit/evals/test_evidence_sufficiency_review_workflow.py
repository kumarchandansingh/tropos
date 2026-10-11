from datetime import UTC, datetime
from pathlib import Path

import pytest

from tropos.evals.contracts import EvalApproval
from tropos.evals.evidence_sufficiency import load_evidence_sufficiency_benchmark
from tropos.evals.evidence_sufficiency_review_workflow import (
    agreement_summary,
    export_adjudication_packet,
    export_review_packet,
    import_adjudication_packet,
    import_review_packet,
)


def _dataset_path() -> Path:
    return (
        Path(__file__).parents[3]
        / "evals"
        / "resolve"
        / "evidence_sufficiency_candidates_v1.json"
    )


def _fill_review_packet(path: Path, *, reviewer: str, label: str, reason: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    import csv
    from io import StringIO

    source = StringIO(text)
    reader = csv.DictReader(source)
    rows = list(reader)
    for row in rows[:2]:
        row["Reviewer"] = reviewer
        row["Review Date"] = datetime(2026, 10, 11, tzinfo=UTC).isoformat()
        row["Label"] = label
        row["Reason Code"] = reason
        row["Required Facts"] = "fact one"
        row["Missing Facts"] = "" if label == "SUFFICIENT" else "missing fact"
        row["Confidence"] = "4"
        row["Would you answer?"] = "YES" if label == "SUFFICIENT" else "NO"
        row["Notes"] = "independent review"
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(output.getvalue(), encoding="utf-8-sig")


def test_review_packet_round_trip_preserves_candidate_content(tmp_path: Path) -> None:
    benchmark = load_evidence_sufficiency_benchmark(_dataset_path())
    packet = tmp_path / "review.csv"

    export_review_packet(benchmark, packet, reviewer="reviewer-a")
    _fill_review_packet(packet, reviewer="reviewer-a", label="SUFFICIENT", reason="NONE")
    updated = import_review_packet(benchmark, packet)

    assert updated.candidate_count == 16
    assert updated.approved_count == 0
    assert len(updated.cases[0].reviews) == 1
    assert updated.cases[0].reviews[0].reviewer == "reviewer-a"
    assert updated.cases[0].query == benchmark.cases[0].query
    assert updated.cases[0].evidence == benchmark.cases[0].evidence
    assert updated.cases[0].source_references == benchmark.cases[0].source_references


def test_second_review_builds_observed_agreement_report(tmp_path: Path) -> None:
    benchmark = load_evidence_sufficiency_benchmark(_dataset_path())

    packet_a = tmp_path / "a.csv"
    export_review_packet(benchmark, packet_a, reviewer="reviewer-a")
    _fill_review_packet(packet_a, reviewer="reviewer-a", label="SUFFICIENT", reason="NONE")
    first = import_review_packet(benchmark, packet_a)

    packet_b = tmp_path / "b.csv"
    export_review_packet(first, packet_b, reviewer="reviewer-b")
    _fill_review_packet(
        packet_b,
        reviewer="reviewer-b",
        label="INSUFFICIENT",
        reason="MISSING_CRITICAL_FACT",
    )
    second = import_review_packet(first, packet_b)

    report = agreement_summary(second)

    assert report["double_reviewed_case_count"] == 2
    assert report["label_agreement"] == 0.0
    assert report["label_reason_agreement"] == 0.0
    assert report["disagreement_case_ids"] == [
        benchmark.cases[0].case_id,
        benchmark.cases[1].case_id,
    ]


def test_duplicate_reviewer_import_is_rejected(tmp_path: Path) -> None:
    benchmark = load_evidence_sufficiency_benchmark(_dataset_path())
    packet = tmp_path / "review.csv"
    export_review_packet(benchmark, packet, reviewer="reviewer-a")
    _fill_review_packet(packet, reviewer="reviewer-a", label="SUFFICIENT", reason="NONE")

    first = import_review_packet(benchmark, packet)

    with pytest.raises(ValueError, match="already has a recorded review"):
        import_review_packet(first, packet)


def test_adjudication_atomically_promotes_reviewed_cases(tmp_path: Path) -> None:
    benchmark = load_evidence_sufficiency_benchmark(_dataset_path())
    review_packet = tmp_path / "review.csv"
    export_review_packet(benchmark, review_packet, reviewer="reviewer-a")
    _fill_review_packet(
        review_packet,
        reviewer="reviewer-a",
        label="INSUFFICIENT",
        reason="MISSING_CRITICAL_FACT",
    )
    reviewed = import_review_packet(benchmark, review_packet)

    adjudication_packet = tmp_path / "adjudication.csv"
    export_adjudication_packet(reviewed, adjudication_packet)

    import csv

    with adjudication_packet.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames
    assert fieldnames is not None

    first = rows[0]
    first["Adjudicator"] = "lead-reviewer"
    first["Adjudicated At"] = datetime(2026, 10, 11, 12, tzinfo=UTC).isoformat()
    first["Label"] = "INSUFFICIENT"
    first["Reason Code"] = "MISSING_CRITICAL_FACT"
    first["Required Facts"] = "fact one"
    first["Missing Facts"] = "missing fact"
    first["Confidence"] = "5"
    first["Would you answer?"] = "NO"
    first["Notes"] = "final adjudication"

    with adjudication_packet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    promoted = import_adjudication_packet(reviewed, adjudication_packet)

    assert promoted.cases[0].approval is EvalApproval.APPROVED
    assert promoted.cases[0].adjudication is not None
    assert promoted.cases[0].adjudication.reviewer == "lead-reviewer"
    assert promoted.cases[1].approval is EvalApproval.CANDIDATE


def test_adjudication_requires_prior_human_review(tmp_path: Path) -> None:
    benchmark = load_evidence_sufficiency_benchmark(_dataset_path())
    packet = tmp_path / "adjudication.csv"

    import csv

    with packet.open("w", encoding="utf-8-sig", newline="") as handle:
        from tropos.evals.evidence_sufficiency_review_workflow import ADJUDICATION_COLUMNS

        writer = csv.DictWriter(handle, fieldnames=ADJUDICATION_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "Case ID": benchmark.cases[0].case_id,
                "Split": benchmark.cases[0].split.value,
                "Query": benchmark.cases[0].query,
                "Review Summary": "",
                "Adjudicator": "lead-reviewer",
                "Adjudicated At": datetime(2026, 10, 11, tzinfo=UTC).isoformat(),
                "Label": "SUFFICIENT",
                "Reason Code": "NONE",
                "Required Facts": "fact one",
                "Missing Facts": "",
                "Confidence": "5",
                "Would you answer?": "YES",
                "Notes": "",
            }
        )

    with pytest.raises(ValueError, match="requires human review"):
        import_adjudication_packet(benchmark, packet)
