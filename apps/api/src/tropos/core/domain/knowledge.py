from dataclasses import dataclass
from datetime import datetime

from tropos.core.domain.access import AccessPolicy

_HEXADECIMAL_CHARACTERS = frozenset("0123456789abcdefABCDEF")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information")


def _validate_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in _HEXADECIMAL_CHARACTERS for character in value):
        raise ValueError(f"{field_name} must be a 64-character hexadecimal SHA-256 digest")


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """Retrieval-ready canonical knowledge with access and processing provenance."""

    knowledge_id: str
    source_system: str
    source_record_id: str
    source_version: str
    content_type: str
    title: str
    content: str
    access_policy: AccessPolicy
    raw_payload_fingerprint: str
    ingestion_fingerprint: str
    normalized_content_fingerprint: str
    normalization_strategy_version: str
    captured_at: datetime
    source_uri: str | None = None
    source_updated_at: datetime | None = None

    def __post_init__(self) -> None:
        required_text = {
            "knowledge_id": self.knowledge_id,
            "source_system": self.source_system,
            "source_record_id": self.source_record_id,
            "source_version": self.source_version,
            "content_type": self.content_type,
            "title": self.title,
            "content": self.content,
            "normalization_strategy_version": self.normalization_strategy_version,
        }

        for field_name, value in required_text.items():
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")

        if not isinstance(self.access_policy, AccessPolicy):
            raise TypeError("access_policy must be an AccessPolicy")

        if not self.access_policy.is_indexable:
            raise ValueError("access_policy must be resolved before creating a knowledge document")

        _validate_sha256(self.raw_payload_fingerprint, "raw_payload_fingerprint")
        _validate_sha256(self.ingestion_fingerprint, "ingestion_fingerprint")
        _validate_sha256(
            self.normalized_content_fingerprint,
            "normalized_content_fingerprint",
        )

        _validate_aware_datetime(self.captured_at, "captured_at")

        if self.source_uri is not None and not self.source_uri.strip():
            raise ValueError("source_uri must not be blank when provided")

        if self.source_updated_at is not None:
            _validate_aware_datetime(
                self.source_updated_at,
                "source_updated_at",
            )


@dataclass(frozen=True, slots=True)
class RetrievedKnowledge:
    """One retrieved document and its normalized relevance score."""

    document: KnowledgeDocument
    score: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between 0.0 and 1.0")
