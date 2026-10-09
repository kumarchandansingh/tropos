"""Stable evidence identity shared across Tropos capabilities."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Durable reference to the exact governed chunk supporting a generated claim."""

    chunk_id: str
    knowledge_id: str
    source_system: str
    source_record_id: str
    source_version: str
    locator: str
    content_fingerprint: str

    def __post_init__(self) -> None:
        required = {
            "chunk_id": self.chunk_id,
            "knowledge_id": self.knowledge_id,
            "source_system": self.source_system,
            "source_record_id": self.source_record_id,
            "source_version": self.source_version,
            "locator": self.locator,
            "content_fingerprint": self.content_fingerprint,
        }
        for field_name, value in required.items():
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")
