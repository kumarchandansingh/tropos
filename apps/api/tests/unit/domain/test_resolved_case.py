from datetime import UTC, datetime

import pytest

from tropos.domain.resolved_case import ResolvedCase


def build_resolved_case(
    *,
    case_id: str = "CASE-001",
    source_system: str = "test-source",
    resolved_at: datetime | None = None,
) -> ResolvedCase:
    return ResolvedCase(
        case_id=case_id,
        source_system=source_system,
        source_record_id="SOURCE-001",
        title="Login failure",
        problem_summary="Customer could not authenticate.",
        resolution_summary="Reset the expired authentication credential.",
        resolved_at=resolved_at or datetime(2026, 9, 19, tzinfo=UTC),
    )


def test_accepts_a_valid_resolved_case() -> None:
    resolved_case = build_resolved_case()

    assert resolved_case.case_id == "CASE-001"


def test_allows_blank_evidence_for_later_assessment() -> None:
    resolved_case = ResolvedCase(
        case_id="CASE-002",
        source_system="test-source",
        source_record_id="SOURCE-002",
        title="",
        problem_summary="",
        resolution_summary="",
        resolved_at=datetime(2026, 9, 19, tzinfo=UTC),
    )

    assert resolved_case.resolution_summary == ""


def test_rejects_a_timestamp_without_timezone() -> None:
    with pytest.raises(
        ValueError,
        match="resolved_at must include timezone information",
    ):
        build_resolved_case(resolved_at=datetime(2026, 9, 19))
