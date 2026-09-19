from datetime import UTC, datetime, timedelta

import pytest

from tropos.application.ingestion.raw_record import RawKnowledgeRecord


def build_record(
    *,
    source_record_id: str = "ARTICLE-001",
    payload: bytes = b'{"title":"Credential reset"}',
    captured_at: datetime | None = None,
    access_groups: tuple[str, ...] = ("support-agent",),
) -> RawKnowledgeRecord:
    return RawKnowledgeRecord(
        source_system="test-knowledge-base",
        source_record_id=source_record_id,
        source_version="1",
        content_type="application/json",
        payload=payload,
        captured_at=captured_at or datetime(2026, 9, 19, tzinfo=UTC),
        access_groups=access_groups,
    )


def test_same_logical_record_has_same_fingerprint() -> None:
    first = build_record(captured_at=datetime(2026, 9, 19, 10, 0, tzinfo=UTC))
    second = build_record(captured_at=datetime(2026, 9, 19, 11, 0, tzinfo=UTC))

    assert first.fingerprint == second.fingerprint


def test_changed_payload_has_different_fingerprint() -> None:
    first = build_record(payload=b'{"title":"Credential reset"}')
    second = build_record(payload=b'{"title":"Updated credential reset"}')

    assert first.fingerprint != second.fingerprint


def test_access_group_order_does_not_change_fingerprint() -> None:
    first = build_record(access_groups=("support-agent", "knowledge-manager"))
    second = build_record(access_groups=("knowledge-manager", "support-agent"))

    assert first.fingerprint == second.fingerprint


def test_blank_source_record_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="source_record_id must not be blank"):
        build_record(source_record_id=" ")


def test_empty_payload_is_rejected() -> None:
    with pytest.raises(ValueError, match="payload must not be empty"):
        build_record(payload=b"")


def test_timestamp_without_timezone_is_rejected() -> None:
    naive_timestamp = datetime.now(tz=UTC).replace(tzinfo=None)
    future_naive_timestamp = naive_timestamp + timedelta(minutes=1)

    with pytest.raises(
        ValueError,
        match="captured_at must include timezone information",
    ):
        build_record(captured_at=future_naive_timestamp)
