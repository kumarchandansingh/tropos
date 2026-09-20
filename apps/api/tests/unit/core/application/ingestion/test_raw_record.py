from datetime import UTC, datetime

import pytest

from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.domain.access import AccessPolicy, AccessScope


def build_record(
    *,
    source_record_id: str = "ARTICLE-001",
    payload: bytes = b'{"title":"Credential reset"}',
    tenant_id: str = "acme",
    access_scope: AccessScope = AccessScope.TENANT,
    captured_at: datetime | None = None,
    allowed_groups: tuple[str, ...] = (),
) -> RawKnowledgeRecord:
    access_policy = AccessPolicy(
        tenant_id=tenant_id,
        scope=access_scope,
        allowed_groups=allowed_groups,
    )

    return RawKnowledgeRecord(
        source_system="test-knowledge-base",
        source_record_id=source_record_id,
        source_version="1",
        content_type="application/json",
        payload=payload,
        access_policy=access_policy,
        captured_at=captured_at or datetime(2026, 9, 19, tzinfo=UTC),
    )


def test_same_logical_record_has_same_ingestion_fingerprint() -> None:
    first = build_record(captured_at=datetime(2026, 9, 19, 10, 0, tzinfo=UTC))
    second = build_record(captured_at=datetime(2026, 9, 19, 11, 0, tzinfo=UTC))

    assert first.ingestion_fingerprint == second.ingestion_fingerprint
    assert first.fingerprint == first.ingestion_fingerprint


def test_raw_payload_fingerprint_tracks_exact_bytes_only() -> None:
    first = build_record(payload=b"same bytes", tenant_id="acme")
    second = build_record(payload=b"same bytes", tenant_id="globex")
    changed = build_record(payload=b"different bytes", tenant_id="acme")

    assert first.raw_payload_fingerprint == second.raw_payload_fingerprint
    assert first.raw_payload_fingerprint != changed.raw_payload_fingerprint
    assert first.ingestion_fingerprint != second.ingestion_fingerprint


def test_changed_payload_has_different_ingestion_fingerprint() -> None:
    first = build_record(payload=b'{"title":"Credential reset"}')
    second = build_record(payload=b'{"title":"Updated credential reset"}')

    assert first.ingestion_fingerprint != second.ingestion_fingerprint


def test_access_group_order_does_not_change_ingestion_fingerprint() -> None:
    first = build_record(
        access_scope=AccessScope.RESTRICTED,
        allowed_groups=("support-agent", "knowledge-manager"),
    )
    second = build_record(
        access_scope=AccessScope.RESTRICTED,
        allowed_groups=("knowledge-manager", "support-agent"),
    )

    assert first.ingestion_fingerprint == second.ingestion_fingerprint


def test_access_group_change_changes_ingestion_fingerprint() -> None:
    first = build_record(
        access_scope=AccessScope.RESTRICTED,
        allowed_groups=("support-agent",),
    )
    second = build_record(
        access_scope=AccessScope.RESTRICTED,
        allowed_groups=("knowledge-manager",),
    )

    assert first.ingestion_fingerprint != second.ingestion_fingerprint


def test_access_scope_change_changes_ingestion_fingerprint() -> None:
    tenant_record = build_record(access_scope=AccessScope.TENANT)
    unresolved_record = build_record(access_scope=AccessScope.UNRESOLVED)

    assert tenant_record.ingestion_fingerprint != unresolved_record.ingestion_fingerprint


def test_blank_source_record_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="source_record_id must not be blank"):
        build_record(source_record_id=" ")


def test_empty_payload_is_rejected() -> None:
    with pytest.raises(ValueError, match="payload must not be empty"):
        build_record(payload=b"")


def test_timestamp_without_timezone_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="captured_at must include timezone information",
    ):
        build_record(captured_at=datetime(2026, 9, 19))


def test_restricted_scope_requires_an_allowed_group() -> None:
    with pytest.raises(
        ValueError,
        match="restricted access requires at least one group",
    ):
        build_record(access_scope=AccessScope.RESTRICTED)


def test_tenant_scope_rejects_allowed_groups() -> None:
    with pytest.raises(
        ValueError,
        match="allowed_groups are valid only for restricted access",
    ):
        build_record(
            access_scope=AccessScope.TENANT,
            allowed_groups=("support-agent",),
        )


def test_blank_allowed_group_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="allowed_groups must not contain blank values",
    ):
        build_record(
            access_scope=AccessScope.RESTRICTED,
            allowed_groups=(" ",),
        )
