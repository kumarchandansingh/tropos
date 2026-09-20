from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord
from tropos.core.domain.knowledge import KnowledgeDocument

_HEXADECIMAL_CHARACTERS = frozenset("0123456789abcdefABCDEF")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in _HEXADECIMAL_CHARACTERS for character in value)


class TextFormat(StrEnum):
    """Structural hint supplied by a source-format extractor."""

    PLAIN = "plain"
    MARKDOWN = "markdown"


class StructuralBlockKind(StrEnum):
    """Normalized structure that participates in canonical content identity."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"


@dataclass(frozen=True, slots=True)
class StructuralBlock:
    """One deterministic structural unit extracted from normalized text."""

    kind: StructuralBlockKind
    text: str
    level: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, StructuralBlockKind):
            raise TypeError("kind must be a StructuralBlockKind")
        if not self.text.strip():
            raise ValueError("block text must not be blank")

        if self.kind is StructuralBlockKind.HEADING:
            if self.level is None or not 1 <= self.level <= 6:
                raise ValueError("heading level must be between 1 and 6")
        elif self.level is not None:
            raise ValueError("level is valid only for heading blocks")


@dataclass(frozen=True, slots=True)
class ExtractedKnowledgeText:
    """Text and basic structure metadata produced from an immutable raw record."""

    raw_record: RawKnowledgeRecord
    title: str
    text: str
    text_format: TextFormat
    source_uri: str | None = None
    source_updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.raw_record, RawKnowledgeRecord):
            raise TypeError("raw_record must be a RawKnowledgeRecord")
        if not self.title.strip():
            raise ValueError("title must not be blank")
        if not self.text.strip():
            raise ValueError("text must not be blank")
        if not isinstance(self.text_format, TextFormat):
            raise TypeError("text_format must be a TextFormat")
        if self.source_uri is not None and not self.source_uri.strip():
            raise ValueError("source_uri must not be blank when provided")
        if self.source_updated_at is not None and (
            self.source_updated_at.tzinfo is None
            or self.source_updated_at.utcoffset() is None
        ):
            raise ValueError("source_updated_at must include timezone information")


@dataclass(frozen=True, slots=True)
class NormalizedKnowledge:
    """Deterministic Level-1/Level-2 representation used for version comparison."""

    source: ExtractedKnowledgeText
    title: str
    normalized_source_text: str
    canonical_text: str
    blocks: tuple[StructuralBlock, ...]
    canonical_serialization: str
    content_fingerprint: str
    strategy_version: str

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("normalized title must not be blank")
        if not self.normalized_source_text.strip():
            raise ValueError("normalized_source_text must not be blank")
        if not self.canonical_text.strip():
            raise ValueError("canonical_text must not be blank")
        if not self.blocks:
            raise ValueError("normalized knowledge must contain at least one block")
        if not self.canonical_serialization:
            raise ValueError("canonical_serialization must not be empty")
        if not _is_sha256(self.content_fingerprint):
            raise ValueError("content_fingerprint must be a SHA-256 digest")
        expected_fingerprint = sha256(self.canonical_serialization.encode("utf-8")).hexdigest()
        if expected_fingerprint != self.content_fingerprint:
            raise ValueError("content_fingerprint must match canonical_serialization")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be blank")


def materialize_knowledge_document(
    *,
    knowledge_id: str,
    normalized: NormalizedKnowledge,
) -> KnowledgeDocument:
    """Create the governed document only after deterministic normalization."""

    raw = normalized.source.raw_record
    return KnowledgeDocument(
        knowledge_id=knowledge_id,
        source_system=raw.source_system,
        source_record_id=raw.source_record_id,
        source_version=raw.source_version,
        content_type=raw.content_type,
        title=normalized.title,
        content=normalized.canonical_text,
        access_policy=raw.access_policy,
        raw_payload_fingerprint=raw.raw_payload_fingerprint,
        ingestion_fingerprint=raw.ingestion_fingerprint,
        normalized_content_fingerprint=normalized.content_fingerprint,
        normalization_strategy_version=normalized.strategy_version,
        captured_at=raw.captured_at,
        source_uri=normalized.source.source_uri,
        source_updated_at=normalized.source.source_updated_at,
    )
