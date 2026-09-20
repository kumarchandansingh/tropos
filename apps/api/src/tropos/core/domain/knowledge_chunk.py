from dataclasses import dataclass
from hashlib import sha256

from tropos.core.domain.access import AccessPolicy
from tropos.core.domain.knowledge import KnowledgeDocument

_HEXADECIMAL_CHARACTERS = frozenset("0123456789abcdefABCDEF")


def text_fingerprint(text: str) -> str:
    """Return a stable SHA-256 fingerprint for exact chunk text."""

    return sha256(text.encode("utf-8")).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in _HEXADECIMAL_CHARACTERS for character in value)


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """An exact, access-controlled occurrence within one canonical content version."""

    chunk_id: str
    knowledge_id: str
    source_system: str
    source_record_id: str
    source_version: str
    document_title: str
    sequence_number: int
    text: str
    start_offset: int
    end_offset: int
    content_fingerprint: str
    ingestion_fingerprint: str
    normalized_content_fingerprint: str
    normalization_strategy_version: str
    access_policy: AccessPolicy
    strategy_version: str

    def __post_init__(self) -> None:
        required_text = {
            "chunk_id": self.chunk_id,
            "knowledge_id": self.knowledge_id,
            "source_system": self.source_system,
            "source_record_id": self.source_record_id,
            "source_version": self.source_version,
            "document_title": self.document_title,
            "normalization_strategy_version": self.normalization_strategy_version,
            "strategy_version": self.strategy_version,
        }
        for field_name, value in required_text.items():
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")

        if self.sequence_number < 0:
            raise ValueError("sequence_number must not be negative")
        if self.start_offset < 0 or self.end_offset <= self.start_offset:
            raise ValueError("chunk offsets must describe a non-empty range")
        if len(self.text) != self.end_offset - self.start_offset:
            raise ValueError("chunk text length must match its source range")
        if self.content_fingerprint != text_fingerprint(self.text):
            raise ValueError("content_fingerprint must match chunk text")
        if not _is_sha256(self.ingestion_fingerprint):
            raise ValueError("ingestion_fingerprint must be a SHA-256 digest")
        if not _is_sha256(self.normalized_content_fingerprint):
            raise ValueError("normalized_content_fingerprint must be a SHA-256 digest")
        if not self.access_policy.is_indexable:
            raise ValueError("a chunk cannot have unresolved access")


def validate_chunk_set(
    *,
    document: KnowledgeDocument,
    chunks: tuple[KnowledgeChunk, ...],
) -> None:
    """Prove that chunks exactly and contiguously cover a canonical document."""

    if not chunks:
        raise ValueError("chunks must not be empty")

    expected_start = 0
    expected_metadata = (
        document.knowledge_id,
        document.source_system,
        document.source_record_id,
        document.source_version,
        document.title,
        document.ingestion_fingerprint,
        document.normalized_content_fingerprint,
        document.normalization_strategy_version,
        document.access_policy,
    )
    strategy_version = chunks[0].strategy_version
    seen_ids: set[str] = set()

    for expected_sequence, chunk in enumerate(chunks):
        if chunk.sequence_number != expected_sequence:
            raise ValueError("chunk sequence must be contiguous")
        if chunk.chunk_id in seen_ids:
            raise ValueError("chunk IDs must be unique")
        seen_ids.add(chunk.chunk_id)
        if chunk.start_offset != expected_start:
            raise ValueError("chunks must not contain gaps or overlaps")
        if chunk.text != document.content[chunk.start_offset : chunk.end_offset]:
            raise ValueError("chunk text must match its exact source range")

        actual_metadata = (
            chunk.knowledge_id,
            chunk.source_system,
            chunk.source_record_id,
            chunk.source_version,
            chunk.document_title,
            chunk.ingestion_fingerprint,
            chunk.normalized_content_fingerprint,
            chunk.normalization_strategy_version,
            chunk.access_policy,
        )
        if actual_metadata != expected_metadata:
            raise ValueError("chunk metadata must match the source document")
        if chunk.strategy_version != strategy_version:
            raise ValueError("all chunks must use the same strategy version")

        expected_start = chunk.end_offset

    if expected_start != len(document.content):
        raise ValueError("chunks must cover the complete document")
