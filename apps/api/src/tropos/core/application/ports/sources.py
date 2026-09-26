from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from tropos.core.application.ingestion.raw_record import RawKnowledgeRecord


class SourceCaptureError(RuntimeError):
    """Base error raised when source capture cannot complete safely."""


class RetryableSourceError(SourceCaptureError):
    """Base error for transient source failures that may succeed on retry."""


class SourceUnavailableError(RetryableSourceError):
    """Raised for transient source/network/service unavailability."""


class SourceRateLimitedError(RetryableSourceError):
    """Raised when the source asks the connector to retry after throttling."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        if retry_after_seconds is not None and retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be non-negative when provided")
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class SourceAuthenticationError(SourceCaptureError):
    """Raised when source authentication cannot be recovered inside the adapter."""


class SourceConfigurationError(SourceCaptureError):
    """Raised when connector configuration prevents safe source access."""


class SourceRecordNotFoundError(SourceCaptureError):
    """Raised when a requested source record does not exist."""


class UnsupportedSourceArtifactError(SourceCaptureError):
    """Raised when a connector cannot map an artifact to a supported content type."""


class SourceIdentityMismatchError(SourceCaptureError):
    """Raised when connector output claims a different source namespace."""


@dataclass(frozen=True, slots=True)
class SourceCapture:
    """Source-adapter output passed into the reusable ingestion pipeline."""

    raw_record: RawKnowledgeRecord
    source_uri: str | None = None
    source_updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.raw_record, RawKnowledgeRecord):
            raise TypeError("raw_record must be a RawKnowledgeRecord")
        if self.source_uri is not None and not self.source_uri.strip():
            raise ValueError("source_uri must not be blank when provided")
        if self.source_updated_at is not None and (
            self.source_updated_at.tzinfo is None or self.source_updated_at.utcoffset() is None
        ):
            raise ValueError("source_updated_at must include timezone information")


class KnowledgeSourceConnector(Protocol):
    """Capture one source-native record without leaking vendor SDK types inward."""

    @property
    def source_namespace(self) -> str:
        """Stable configured source-instance namespace used in source identity."""
        ...

    def capture(self, source_record_id: str) -> SourceCapture:
        """Return an immutable capture for one source-native record identifier."""
        ...
