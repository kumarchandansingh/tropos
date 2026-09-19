from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256


class AccessScope(StrEnum):
    """Access state received from the source-system connector."""

    UNRESOLVED = "UNRESOLVED"
    TENANT = "TENANT"
    RESTRICTED = "RESTRICTED"


@dataclass(frozen=True, slots=True)
class RawKnowledgeRecord:
    """Immutable source record received by the ingestion boundary."""

    source_system: str
    source_record_id: str
    source_version: str
    content_type: str
    payload: bytes
    access_scope: AccessScope
    captured_at: datetime
    allowed_groups: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_system.strip():
            raise ValueError("source_system must not be blank")

        if not self.source_record_id.strip():
            raise ValueError("source_record_id must not be blank")

        if not self.source_version.strip():
            raise ValueError("source_version must not be blank")

        if not self.content_type.strip():
            raise ValueError("content_type must not be blank")

        if not self.payload:
            raise ValueError("payload must not be empty")

        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must include timezone information")

        if any(not group.strip() for group in self.allowed_groups):
            raise ValueError("allowed_groups must not contain blank values")

        if len(set(self.allowed_groups)) != len(self.allowed_groups):
            raise ValueError("allowed_groups must not contain duplicates")

        if self.access_scope is AccessScope.RESTRICTED and not self.allowed_groups:
            raise ValueError("restricted records must contain at least one allowed group")

        if self.access_scope is not AccessScope.RESTRICTED and self.allowed_groups:
            raise ValueError("allowed_groups are valid only for restricted records")

    @property
    def fingerprint(self) -> str:
        """Return a stable identity for idempotent processing."""

        digest = sha256()

        identity_values = (
            self.source_system,
            self.source_record_id,
            self.source_version,
            self.content_type,
            self.access_scope.value,
            *sorted(self.allowed_groups),
        )

        for value in identity_values:
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")

        digest.update(self.payload)

        return digest.hexdigest()
