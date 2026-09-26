from datetime import datetime
from typing import Protocol

from tropos.core.application.ingestion.normalization import ExtractedKnowledgeText
from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord


class KnowledgeParseError(ValueError):
    """Raised when a supported source cannot be parsed safely."""


class UnsupportedContentTypeError(KnowledgeParseError):
    """Raised when no parser is registered for a source content type."""


class KnowledgeParser(Protocol):
    """Convert immutable source bytes into normalized parser output."""

    def parse(
        self,
        raw_record: RawKnowledgeRecord,
        *,
        source_uri: str | None = None,
        source_updated_at: datetime | None = None,
    ) -> ExtractedKnowledgeText: ...
