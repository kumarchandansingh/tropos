import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import ClassVar

from tropos.core.domain.access import AccessPolicy


@dataclass(frozen=True, slots=True)
class RawKnowledgeRecord:
    """Immutable source record received by the ingestion boundary."""

    FINGERPRINT_SCHEMA_VERSION: ClassVar[int] = 1

    source_system: str
    source_record_id: str
    source_version: str
    content_type: str
    payload: bytes
    access_policy: AccessPolicy
    captured_at: datetime

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

        if not isinstance(self.access_policy, AccessPolicy):
            raise TypeError("access_policy must be an AccessPolicy")

        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must include timezone information")

    @property
    def fingerprint(self) -> str:
        """Return a stable identity for idempotent processing."""

        metadata = {
            "access_policy": {
                "allowed_groups": self.access_policy.allowed_groups,
                "scope": self.access_policy.scope.value,
                "tenant_id": self.access_policy.tenant_id,
            },
            "content_type": self.content_type,
            "fingerprint_schema_version": self.FINGERPRINT_SCHEMA_VERSION,
            "source_record_id": self.source_record_id,
            "source_system": self.source_system,
            "source_version": self.source_version,
        }

        canonical_metadata = json.dumps(
            metadata,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

        digest = sha256()
        digest.update(canonical_metadata)
        digest.update(b"\0")
        digest.update(self.payload)

        return digest.hexdigest()
